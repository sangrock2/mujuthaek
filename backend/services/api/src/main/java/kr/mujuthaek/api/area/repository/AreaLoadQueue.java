package kr.mujuthaek.api.area.repository;

import java.sql.Date;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Duration;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.area.domain.AreaLoadRequest;
import kr.mujuthaek.api.area.domain.AreaSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * area 적재 대기열 (area.load_runs의 PENDING 행). 수신기는 {@link #request}로 남기고 바로 끝나고, 작업자가 {@link
 * #claimNext}로 하나씩 꺼내 적재해요. 같은 파일(원천·범위·지문)은 기다리거나 도는 요청이 하나만 있어요 (load_runs_open_file_uq).
 */
@Component
public class AreaLoadQueue {

  /** 같은 파일을 이만큼 꺼내 적재하고도 끝나지 않으면 더 넣지 않아요 (FAILED로 남겨 사람이 봐요). */
  public static final int MAX_ATTEMPTS = 3;

  private final JdbcTemplate jdbc;

  public AreaLoadQueue(JdbcTemplate jdbc) {
    this.jdbc = jdbc;
  }

  public enum Requested {
    /** 새로 기다리게 넣었어요 */
    QUEUED,
    /** 같은 파일이 이미 성공해서 SKIPPED로 남겼어요 */
    ALREADY_LOADED,
    /** 같은 파일이 이미 기다리거나 도는 중이에요 */
    IN_PROGRESS
  }

  /** 꺼낸 요청 하나 (상태는 RUNNING). */
  public record Claimed(UUID runId, AreaLoadRequest request, int attempts) {}

  /** 멈춘 채 남아 있던 기록을 닫은 결과. */
  public record Recovered(AreaLoadRequest request, int attempts, boolean requeued) {}

  /**
   * 적재 요청을 남겨요. 실패한 파일을 다시 올리면(같은 지문) 새로 기다리게 넣어요.
   *
   * <p>같은 원천·범위·지문 잠금 안에서 확인하고 넣어서, 같은 요청이 동시에 와도 하나만 들어가요.
   */
  @Transactional
  public Requested request(AreaLoadRequest r) {
    jdbc.queryForObject(
        "select pg_advisory_xact_lock(hashtext(?))",
        Object.class,
        "area.queue:" + r.source().name() + ":" + r.scope() + ":" + r.sha256());
    if (exists(r, "'SUCCEEDED'")) {
      insert(r, "SKIPPED", 0);
      return Requested.ALREADY_LOADED;
    }
    if (exists(r, "'PENDING', 'RUNNING'")) {
      return Requested.IN_PROGRESS;
    }
    insert(r, "PENDING", 0);
    return Requested.QUEUED;
  }

  /** 가장 먼저 들어온 PENDING 하나를 RUNNING으로 바꿔 꺼내요. 여러 서버가 같이 꺼내도 겹치지 않아요(skip locked). */
  @Transactional
  public Optional<Claimed> claimNext() {
    return jdbc
        .query(
            """
            update area.load_runs set status = 'RUNNING', started_at = now(), attempts = attempts + 1
             where id = (select id from area.load_runs
                          where status = 'PENDING' and next_attempt_at <= now()
                          order by next_attempt_at, started_at
                          limit 1
                          for update skip locked)
            returning id, source, load_scope, file_key, file_sha256, data_date, allow_shrink, attempts
            """,
            (rs, i) ->
                new Claimed(rs.getObject("id", UUID.class), request(rs), rs.getInt("attempts")))
        .stream()
        .findFirst();
  }

  /**
   * 적재 중 예외(S3·DB 연결 오류 등)로 끝나지 못한 기록. 횟수가 남았으면 잠깐 뒤 다시 꺼내게 PENDING으로, 아니면 FAILED로 둬요.
   *
   * @return 다시 기다리게 넣었으면 true
   */
  @Transactional
  public boolean release(UUID runId, int attempts, String error, Duration retryAfter) {
    boolean retry = attempts < MAX_ATTEMPTS;
    jdbc.update(
        """
        update area.load_runs
           set status = ?, error = ?,
               next_attempt_at = now() + make_interval(secs => ?),
               finished_at = case when ? then null else now() end
         where id = ? and status = 'RUNNING'
        """,
        retry ? "PENDING" : "FAILED",
        error,
        retryAfter.toSeconds(),
        retry,
        runId);
    return retry;
  }

  /**
   * api가 뜰 때: 남아 있는 RUNNING은 앞선 api가 멈추거나 꺼져 끝내지 못한 것이에요. FAILED로 닫고, 횟수가 남았고 아직 성공한 적 없는 파일은 다시
   * 기다리게 넣어요. 서버가 한 대라서 뜨는 순간 도는 적재는 없어요.
   */
  @Transactional
  public List<Recovered> recoverStale(String error) {
    jdbc.queryForObject(
        "select pg_advisory_xact_lock(hashtext('area.queue.recover'))", Object.class);
    List<Recovered> closed =
        jdbc.query(
            """
            update area.load_runs set status = 'FAILED', error = ?, finished_at = now()
             where status = 'RUNNING'
            returning source, load_scope, file_key, file_sha256, data_date, allow_shrink, attempts
            """,
            (rs, i) -> new Recovered(request(rs), rs.getInt("attempts"), false),
            error);
    return closed.stream()
        .map(
            c -> {
              boolean requeue =
                  c.attempts() < MAX_ATTEMPTS
                      && !exists(c.request(), "'SUCCEEDED'")
                      && !exists(c.request(), "'PENDING', 'RUNNING'");
              if (requeue) {
                insert(c.request(), "PENDING", c.attempts());
              }
              return new Recovered(c.request(), c.attempts(), requeue);
            })
        .toList();
  }

  private boolean exists(AreaLoadRequest r, String statuses) {
    Integer found =
        jdbc.query(
            "select 1 from area.load_runs where source = ? and load_scope = ? and file_sha256 = ?"
                + " and status in ("
                + statuses
                + ") limit 1",
            rs -> rs.next() ? 1 : null,
            r.source().name(),
            r.scope(),
            r.sha256());
    return found != null;
  }

  private void insert(AreaLoadRequest r, String status, int attempts) {
    jdbc.update(
        """
        insert into area.load_runs
            (source, load_scope, file_key, file_sha256, data_date, status, allow_shrink, attempts, finished_at)
        values (?, ?, ?, ?, ?, ?, ?, ?, case when ? = 'SKIPPED' then now() end)
        """,
        r.source().name(),
        r.scope(),
        r.fileKey(),
        r.sha256(),
        Date.valueOf(r.dataDate()),
        status,
        r.allowShrink(),
        attempts,
        status);
  }

  private static AreaLoadRequest request(ResultSet rs) throws SQLException {
    return new AreaLoadRequest(
        AreaSource.valueOf(rs.getString("source")),
        rs.getString("load_scope"),
        rs.getString("file_key"),
        rs.getString("file_sha256"),
        rs.getDate("data_date").toLocalDate(),
        rs.getBoolean("allow_shrink"));
  }
}
