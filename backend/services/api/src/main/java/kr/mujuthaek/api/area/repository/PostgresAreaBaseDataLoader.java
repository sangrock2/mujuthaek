package kr.mujuthaek.api.area.repository;

import java.io.BufferedInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import javax.sql.DataSource;
import kr.mujuthaek.api.area.domain.AreaLoadReport;
import kr.mujuthaek.api.area.domain.AreaLoadRequest;
import kr.mujuthaek.api.area.domain.AreaSource;
import org.postgresql.copy.CopyManager;
import org.postgresql.core.BaseConnection;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * 원천 파일을 area.facilities / area.stores / area.address_points에 반영해요. JDBC만 써서 테스트에서는 {@code new}로
 * 만들어요.
 *
 * <p>순서: 머리줄 확인 → 머리줄 이름 그대로 임시 테이블(stage_raw) → COPY → 변환 SQL(stage_norm) → 공통 검사 → 삭제·반영 → 실행 기록.
 * 데이터 변경은 트랜잭션 하나라 실패하면 이전 데이터가 그대로 남아요. 실행 기록은 실패해도 남아야 해서 커넥션을 직접 잡고 커밋·롤백해요 — 부르는 쪽에
 * {@code @Transactional}을 붙이지 마세요.
 *
 * <p>내용이 같은 줄은 건드리지 않아요(기준일도 그대로). 그래서 줄의 data_date는 "그 줄이 마지막으로 바뀐 적재의 기준일"이고, 원천 파일의 기준일은
 * load_runs.data_date에 남아요. 같은 줄의 기준일까지 맞추면 다시 넣기가 크게 느려져요(서울 상가 55만 줄 다시 넣기 22초 중 15.6초가 기준일 갱신).
 *
 * <p>{@code @Repository}는 예외 변환 프록시(CGLIB)를 만들어 final 클래스에 붙일 수 없어서 {@code @Component}예요.
 */
@Component
public final class PostgresAreaBaseDataLoader {

  private static final String SQL_DIR = "area/load/";
  private static final int SHRINK_GUARD_MIN_ROWS = 100;

  /** 적재 한 번의 SQL이 이보다 오래 걸리면 끊고 FAILED로 끝내요 (DB·S3가 멈춰 끝없이 기다리지 않게). */
  static final Duration DEFAULT_STATEMENT_TIMEOUT = Duration.ofMinutes(90);

  /** 같은 원천·범위 잠금이나 테이블 잠금을 이보다 오래 기다리지 않아요. */
  static final Duration LOCK_TIMEOUT = Duration.ofMinutes(10);

  private final DataSource dataSource;
  private final Duration statementTimeout;
  private final Map<String, String> sqlCache = new ConcurrentHashMap<>();

  public PostgresAreaBaseDataLoader(DataSource dataSource) {
    this(dataSource, DEFAULT_STATEMENT_TIMEOUT);
  }

  @Autowired
  public PostgresAreaBaseDataLoader(
      DataSource dataSource,
      @Value("${mujuthaek.area.load.statement-timeout:90m}") Duration statementTimeout) {
    this.dataSource = dataSource;
    this.statementTimeout = statementTimeout;
  }

  /** 원천 파일 내용을 반영해요. 파일 문제는 FAILED 결과로, DB 연결 문제는 예외로 알려요. */
  public AreaLoadReport load(AreaLoadRequest request, InputStream content) {
    try (Connection conn = dataSource.getConnection()) {
      conn.setAutoCommit(true);
      if (alreadySucceeded(conn, request)) {
        return AreaLoadReport.skipped(insertRun(conn, request, "SKIPPED"));
      }
      return run(conn, request, insertRun(conn, request, "RUNNING"), content);
    } catch (SQLException e) {
      throw new AreaLoadException("적재 기록을 남기지 못했어요: " + e.getMessage(), e);
    }
  }

  /**
   * 대기열에서 꺼낸 실행 기록(RUNNING)을 이어 써요. 그사이 같은 파일이 성공했으면 SKIPPED로 닫아요.
   *
   * @param runId {@link AreaLoadQueue#claimNext()}가 RUNNING으로 바꾼 기록
   */
  public AreaLoadReport loadRun(UUID runId, AreaLoadRequest request, InputStream content) {
    try (Connection conn = dataSource.getConnection()) {
      conn.setAutoCommit(true);
      if (alreadySucceeded(conn, request)) {
        skipRun(conn, runId);
        return AreaLoadReport.skipped(runId);
      }
      return run(conn, request, runId, content);
    } catch (SQLException e) {
      throw new AreaLoadException("적재 기록을 남기지 못했어요: " + e.getMessage(), e);
    }
  }

  private AreaLoadReport run(
      Connection conn, AreaLoadRequest request, UUID runId, InputStream content)
      throws SQLException {
    try {
      conn.setAutoCommit(false);
      limitTime(conn);
      AreaLoadReport report = loadInTransaction(conn, request, runId, content);
      finishRun(conn, report);
      conn.commit();
      return report;
    } catch (Exception e) {
      conn.rollback();
      conn.setAutoCommit(true);
      String message = describe(e);
      failRun(conn, runId, message);
      return AreaLoadReport.failed(runId, message);
    }
  }

  /** 이 트랜잭션에만 시간 제한을 걸어요 (커넥션을 풀에 돌려줄 때 남지 않게 set_config(…, true)). */
  private void limitTime(Connection conn) throws SQLException {
    try (PreparedStatement ps =
        conn.prepareStatement(
            "select set_config('statement_timeout', ?, true), set_config('lock_timeout', ?, true)")) {
      ps.setString(1, statementTimeout.toMillis() + "ms");
      ps.setString(2, LOCK_TIMEOUT.toMillis() + "ms");
      ps.execute();
    }
  }

  private AreaLoadReport loadInTransaction(
      Connection conn, AreaLoadRequest req, UUID runId, InputStream content)
      throws SQLException, IOException {
    AreaSource source = req.source();
    lock(conn, source, req.scope());

    BufferedInputStream in = new BufferedInputStream(content, 1 << 16);
    // 머리줄 없는 원천(도로명주소)은 원천 정의의 고정 칸 이름을 써요.
    List<String> header =
        source.headerless() ? source.requiredColumns() : CsvHeader.read(in, source.charset());
    List<String> missing =
        source.requiredColumns().stream().filter(c -> !header.contains(c)).toList();
    if (!missing.isEmpty()) {
      throw new AreaLoadException("파일에 꼭 있어야 하는 칸이 없어요: " + missing + " (파일의 칸: " + header + ")");
    }

    List<String> columns = safeColumnNames(header);
    try (Statement st = conn.createStatement()) {
      st.execute(createStageRaw(columns));
      st.execute(STAGE_NORM_DDL);
    }
    boolean csvQuotes = source.delimiter() == ',';
    copyRows(
        conn,
        columns,
        source.charset(),
        source.delimiter(),
        new BlankLineSkippingInputStream(in, csvQuotes));

    try (Statement st = conn.createStatement()) {
      st.execute(sql(source.mappingSql()));
      st.execute(sql("validate.sql"));
      // 임시 테이블은 자동 통계가 없어요. 이게 없으면 "파일에 없는 줄 지우기"가 줄 수의 제곱만큼 비교해요.
      st.execute(
          "create index on stage_norm (source_key) where skip_reason is null and reject_reason is null");
      st.execute("analyze stage_norm");
    }

    Counts c = count(conn);
    guardShrink(conn, req, c.accepted);
    Date dataDate = Date.valueOf(req.dataDate());
    int[] iu;
    int deleted;
    // 지우기를 반영보다 먼저 해요. 반영 뒤에 지우면 방금 넣은 줄이 통계에 없어서(첫 적재면 0줄로 봐요) 줄마다 임시 테이블을 통째로 읽어요
    // (경기 상가 67만 줄 첫 적재에서 12분 넘게 걸림). 먼저 지우면 이미 커밋된 줄만 보고, 결과는 같아요.
    switch (source.target()) {
      case FACILITIES -> {
        deleted = update(conn, sql("delete_facilities.sql"), source.name());
        iu =
            queryPair(
                conn, sql("apply_facilities.sql"), source.facilityKind(), source.name(), dataDate);
      }
      // 상가·도로명주소는 시도 파일 하나가 적재 한 번이라, 지우기를 그 시도(load_scope) 안에서만 해요.
      case STORES -> {
        deleted = update(conn, sql("delete_stores.sql"), req.scope());
        iu = queryPair(conn, sql("apply_stores.sql"), req.scope(), dataDate);
        // 상권 입지계수의 분모(업종 묶음별 전국 점포 수)도 같은 트랜잭션에서 다시 채워요
        update(conn, sql("fill_industry_shares.sql"));
      }
      case ADDRESS_POINTS -> {
        deleted = update(conn, sql("delete_address_points.sql"), req.scope());
        iu = queryPair(conn, sql("apply_address_points.sql"), req.scope(), dataDate);
        // 오타 찾기용 도로명 목록도 같은 트랜잭션에서 그 시도 범위만 다시 채워요 (사전과 어긋나지 않게)
        update(conn, sql("delete_road_names.sql"), req.scope());
        update(conn, sql("fill_road_names.sql"), req.scope());
      }
      // 경계는 시군구·법정읍면동이 파일 하나씩이라, 지우기를 그 단계(level) 안에서만 해요.
      case REGION_BOUNDARIES -> {
        deleted = update(conn, sql("delete_region_boundaries.sql"), source.boundaryLevel());
        iu = queryPair(conn, sql("apply_region_boundaries.sql"), source.boundaryLevel(), dataDate);
      }
      default -> throw new IllegalStateException("모르는 적재 대상: " + source.target());
    }
    int inserted = iu[0];
    int updated = iu[1];
    int unchanged = c.accepted - inserted - updated;
    return new AreaLoadReport(
        runId,
        AreaLoadReport.Status.SUCCEEDED,
        c.rowsIn,
        c.skipped,
        c.rejected,
        c.fixed,
        inserted,
        updated,
        unchanged,
        deleted,
        c.rejectReasons,
        null);
  }

  // ── 실행 기록 ────────────────────────────────────────────────────────────

  /** 같은 원천·범위·지문의 성공 기록이 있으면 다시 적재하지 않아요 (같은 이벤트를 두 번 받아도 안전). */
  private static boolean alreadySucceeded(Connection conn, AreaLoadRequest r) throws SQLException {
    try (PreparedStatement ps =
        conn.prepareStatement(
            "select 1 from area.load_runs"
                + " where source = ? and load_scope = ? and file_sha256 = ? and status = 'SUCCEEDED'")) {
      ps.setString(1, r.source().name());
      ps.setString(2, r.scope());
      ps.setString(3, r.sha256());
      try (ResultSet rs = ps.executeQuery()) {
        return rs.next();
      }
    }
  }

  private static UUID insertRun(Connection conn, AreaLoadRequest r, String status)
      throws SQLException {
    try (PreparedStatement ps =
        conn.prepareStatement(
            "insert into area.load_runs (source, load_scope, file_key, file_sha256, data_date, status, finished_at) "
                + "values (?, ?, ?, ?, ?, ?, case when ? = 'SKIPPED' then now() end) returning id")) {
      ps.setString(1, r.source().name());
      ps.setString(2, r.scope());
      ps.setString(3, r.fileKey());
      ps.setString(4, r.sha256());
      ps.setDate(5, Date.valueOf(r.dataDate()));
      ps.setString(6, status);
      ps.setString(7, status);
      try (ResultSet rs = ps.executeQuery()) {
        rs.next();
        return rs.getObject(1, UUID.class);
      }
    }
  }

  /** 데이터와 같은 트랜잭션이라 now()는 트랜잭션 시작 시각이에요. 끝난 시각은 clock_timestamp()로 남겨요. */
  private static void finishRun(Connection conn, AreaLoadReport r) throws SQLException {
    try (PreparedStatement ps =
        conn.prepareStatement(
            "update area.load_runs set status = 'SUCCEEDED', rows_in = ?, rows_skipped = ?, rows_rejected = ?, "
                + "rows_fixed = ?, rows_inserted = ?, rows_updated = ?, rows_unchanged = ?, rows_deleted = ?, "
                + "reject_reasons = ?::jsonb, finished_at = clock_timestamp() where id = ?")) {
      ps.setInt(1, r.rowsIn());
      ps.setInt(2, r.rowsSkipped());
      ps.setInt(3, r.rowsRejected());
      ps.setInt(4, r.rowsFixed());
      ps.setInt(5, r.rowsInserted());
      ps.setInt(6, r.rowsUpdated());
      ps.setInt(7, r.rowsUnchanged());
      ps.setInt(8, r.rowsDeleted());
      ps.setString(9, toJson(r.rejectReasons()));
      ps.setObject(10, r.runId());
      ps.executeUpdate();
    }
  }

  private static void skipRun(Connection conn, UUID runId) throws SQLException {
    try (PreparedStatement ps =
        conn.prepareStatement(
            "update area.load_runs set status = 'SKIPPED', finished_at = now() where id = ?")) {
      ps.setObject(1, runId);
      ps.executeUpdate();
    }
  }

  private static void failRun(Connection conn, UUID runId, String message) throws SQLException {
    try (PreparedStatement ps =
        conn.prepareStatement(
            "update area.load_runs set status = 'FAILED', error = ?, finished_at = now() where id = ?")) {
      ps.setString(1, message);
      ps.setObject(2, runId);
      ps.executeUpdate();
    }
  }

  // ── 단계별 도우미 ─────────────────────────────────────────────────────────

  /** 같은 원천·범위를 동시에 적재하지 않게 트랜잭션 잠금을 걸어요. */
  private static void lock(Connection conn, AreaSource source, String scope) throws SQLException {
    try (PreparedStatement ps =
        conn.prepareStatement("select pg_advisory_xact_lock(hashtext(?))")) {
      ps.setString(1, "area.load:" + source.name() + ":" + scope);
      ps.execute();
    }
  }

  /**
   * 임시 테이블 칸 이름. 원천 칸 이름을 그대로 쓰되, PostgreSQL 이름 길이(63바이트)를 넘거나 비었거나 겹치면 c{번호}로 바꿔요. 변환 SQL이 쓰는 칸은
   * 모두 짧아서 그대로 남아요.
   */
  static List<String> safeColumnNames(List<String> header) {
    List<String> out = new ArrayList<>();
    Set<String> seen = new HashSet<>();
    for (int i = 0; i < header.size(); i++) {
      String name = header.get(i);
      boolean ok =
          !name.isBlank()
              && name.getBytes(StandardCharsets.UTF_8).length <= 60
              && !"line_no".equals(name);
      String chosen = ok && seen.add(name) ? name : "c" + (i + 1);
      seen.add(chosen);
      out.add(chosen);
    }
    return out;
  }

  private static String createStageRaw(List<String> columns) {
    StringBuilder ddl = new StringBuilder("create temp table stage_raw (line_no bigserial");
    for (String c : columns) {
      ddl.append(", ").append(quote(c)).append(" text");
    }
    return ddl.append(") on commit drop").toString();
  }

  private static void copyRows(
      Connection conn, List<String> columns, Charset charset, char delimiter, InputStream rows)
      throws SQLException, IOException {
    String encoding = charset.equals(StandardCharsets.UTF_8) ? "UTF8" : "UHC";
    // | 구분 원천은 값을 따옴표로 감싸지 않아서, 따옴표 문자를 쓰이지 않는 제어 문자로 바꿔 값 안의 "를 그대로 둬요.
    String options =
        delimiter == ','
            ? "format csv, encoding '" + encoding + "'"
            : "format csv, encoding '"
                + encoding
                + "', delimiter '"
                + delimiter
                + "', quote e'\\x01'";
    String copy =
        "copy stage_raw ("
            + String.join(", ", columns.stream().map(PostgresAreaBaseDataLoader::quote).toList())
            + ") from stdin with ("
            + options
            + ")";
    new CopyManager(conn.unwrap(BaseConnection.class)).copyIn(copy, rows);
  }

  private record Counts(
      int rowsIn,
      int skipped,
      int rejected,
      int fixed,
      int accepted,
      Map<String, Integer> rejectReasons) {}

  private static Counts count(Connection conn) throws SQLException {
    int rowsIn;
    int skipped;
    int fixed;
    int accepted;
    try (Statement st = conn.createStatement();
        ResultSet rs =
            st.executeQuery(
                "select (select count(*) from stage_raw), "
                    + "count(*) filter (where skip_reason is not null), "
                    + "count(*) filter (where skip_reason is null and reject_reason is null and fixed), "
                    + "count(*) filter (where skip_reason is null and reject_reason is null) from stage_norm")) {
      rs.next();
      rowsIn = rs.getInt(1);
      skipped = rs.getInt(2);
      fixed = rs.getInt(3);
      accepted = rs.getInt(4);
    }
    Map<String, Integer> reasons = new LinkedHashMap<>();
    int rejected = 0;
    try (Statement st = conn.createStatement();
        ResultSet rs =
            st.executeQuery(
                "select reject_reason, count(*) from stage_norm where reject_reason is not null group by 1 order by 1")) {
      while (rs.next()) {
        reasons.put(rs.getString(1), rs.getInt(2));
        rejected += rs.getInt(2);
      }
    }
    return new Counts(rowsIn, skipped, rejected, fixed, accepted, reasons);
  }

  /** 잘린 파일로 데이터가 크게 지워지지 않게, 쓸 줄이 지금 데이터의 절반 미만이면 멈춰요. 데이터가 적을 때는 보지 않아요. */
  private static void guardShrink(Connection conn, AreaLoadRequest req, int accepted)
      throws SQLException {
    if (req.allowShrink()) {
      return;
    }
    String sql =
        switch (req.source().target()) {
          case STORES -> "select count(*) from area.stores where load_scope = ?";
          case ADDRESS_POINTS -> "select count(*) from area.address_points where load_scope = ?";
          case FACILITIES -> "select count(*) from area.facilities where source = ?";
          case REGION_BOUNDARIES -> "select count(*) from area.region_boundaries where level = ?";
        };
    AreaSource source = req.source();
    String key =
        source.scoped()
            ? req.scope()
            : source.target() == AreaSource.Target.REGION_BOUNDARIES
                ? source.boundaryLevel()
                : source.name();
    try (PreparedStatement ps = conn.prepareStatement(sql)) {
      ps.setString(1, key);
      try (ResultSet rs = ps.executeQuery()) {
        rs.next();
        int existing = rs.getInt(1);
        if (existing >= SHRINK_GUARD_MIN_ROWS && accepted * 2 < existing) {
          throw new AreaLoadException(
              "쓸 수 있는 줄("
                  + accepted
                  + ")이 지금 데이터("
                  + existing
                  + ")의 절반보다 적어요. 파일이 잘렸는지 확인하고, 맞으면 allowShrink로 다시 적재하세요");
        }
      }
    }
  }

  private static int[] queryPair(Connection conn, String sql, Object... params)
      throws SQLException {
    try (PreparedStatement ps = conn.prepareStatement(sql)) {
      bind(ps, params);
      try (ResultSet rs = ps.executeQuery()) {
        rs.next();
        return new int[] {rs.getInt(1), rs.getInt(2)};
      }
    }
  }

  private static int update(Connection conn, String sql, Object... params) throws SQLException {
    try (PreparedStatement ps = conn.prepareStatement(sql)) {
      bind(ps, params);
      return ps.executeUpdate();
    }
  }

  private static void bind(PreparedStatement ps, Object... params) throws SQLException {
    for (int i = 0; i < params.length; i++) {
      ps.setObject(i + 1, params[i]);
    }
  }

  private String sql(String name) {
    return sqlCache.computeIfAbsent(
        name,
        n -> {
          try (InputStream in =
              PostgresAreaBaseDataLoader.class.getClassLoader().getResourceAsStream(SQL_DIR + n)) {
            if (in == null) {
              throw new IllegalStateException("SQL 파일이 없어요: " + SQL_DIR + n);
            }
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
          } catch (IOException e) {
            throw new UncheckedIOException(e);
          }
        });
  }

  private static String quote(String identifier) {
    return "\"" + identifier.replace("\"", "\"\"") + "\"";
  }

  private static String toJson(Map<String, Integer> map) {
    StringBuilder json = new StringBuilder("{");
    map.forEach(
        (k, v) -> {
          if (json.length() > 1) {
            json.append(',');
          }
          json.append('"').append(k.replace("\"", "")).append("\":").append(v);
        });
    return json.append('}').toString();
  }

  private static String describe(Exception e) {
    String message = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
    return message.length() > 2000 ? message.substring(0, 2000) : message;
  }

  private static final String STAGE_NORM_DDL =
      """
      create temp table stage_norm (
          line_no       bigint primary key,
          skip_reason   text,
          reject_reason text,
          fixed         boolean not null default false,
          source_key    text,
          name          text,
          sub_kind      text,
          address       text,
          lat_txt       text,
          lng_txt       text,
          lat           double precision,
          lng           double precision,
          extra         jsonb,
          large_code    text,
          large_name    text,
          middle_code   text,
          middle_name   text,
          small_code    text,
          small_name    text,
          bjd_code      text,
          sido          text,
          sigungu       text,
          emd           text,
          ri            text,
          road_code     text,
          road_name     text,
          underground   text,
          bldg_main     text,
          bldg_sub      text,
          zip_code      text,
          geom          geometry
      ) on commit drop""";
}
