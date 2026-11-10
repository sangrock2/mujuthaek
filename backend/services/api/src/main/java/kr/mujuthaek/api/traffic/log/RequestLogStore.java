package kr.mujuthaek.api.traffic.log;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.Timestamp;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicInteger;
import kr.mujuthaek.api.traffic.TrafficProperties;
import kr.mujuthaek.api.traffic.log.RequestClassifier.Area;
import kr.mujuthaek.api.traffic.log.RequestClassifier.Client;
import kr.mujuthaek.api.traffic.log.RequestClassifier.LoginResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 요청 기록 저장·조회. 요청마다 DB에 쓰지 않고 메모리에 모았다가 몇 초마다 한 번에 넣어요(요청 응답 시간에 영향 없게). 너무 많이 쌓이면(공격 등) 넘치는 기록은
 * 버려요. 매일 11:30에 원본 IP를 지우고 오래된 기록을 지워요.
 */
@Component
public class RequestLogStore {

  public static final ZoneId KST = ZoneId.of("Asia/Seoul");
  private static final Logger log = LoggerFactory.getLogger(RequestLogStore.class);
  private static final int MAX_PENDING = 20_000;

  /** 요청 한 건. ip는 원본, ipHash는 저장 때 계산해요. 화면 요청(PAGE)은 응답 코드·처리 시간을 몰라서 null이에요. */
  public record Entry(
      Instant at,
      String method,
      String path,
      Integer status,
      Integer durationMs,
      Client client,
      String userAgent,
      String ip,
      Area area,
      LoginResult loginResult) {}

  private final JdbcTemplate jdbc;
  private final TrafficProperties props;
  private final Clock clock;
  private final ConcurrentLinkedQueue<Entry> pending = new ConcurrentLinkedQueue<>();
  private final AtomicInteger size = new AtomicInteger();

  public RequestLogStore(JdbcTemplate jdbc, TrafficProperties props, Clock clock) {
    this.jdbc = jdbc;
    this.props = props;
    this.clock = clock;
  }

  /** 기록을 넣을 차례에 올려요. 차례가 가득 차면 버려요. */
  public void add(Entry entry) {
    if (size.incrementAndGet() > MAX_PENDING) {
      size.decrementAndGet();
      return;
    }
    pending.add(entry);
  }

  /** 모인 기록을 한 번에 넣어요. */
  @Scheduled(fixedDelay = 5000)
  public void flush() {
    List<Object[]> rows = new ArrayList<>();
    Entry e;
    while ((e = pending.poll()) != null) {
      size.decrementAndGet();
      rows.add(
          new Object[] {
            Timestamp.from(e.at()),
            e.method(),
            e.path(),
            e.status(),
            e.durationMs(),
            e.client().name(),
            e.userAgent(),
            ipHash(e.ip(), e.at()),
            e.ip(),
            e.area().name(),
            e.loginResult() == null ? null : e.loginResult().name()
          });
    }
    if (rows.isEmpty()) {
      return;
    }
    try {
      jdbc.batchUpdate(
          "insert into traffic.request_logs (occurred_at, method, path, status, duration_ms, client,"
              + " user_agent, ip_hash, ip, area, login_result) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
          rows);
    } catch (RuntimeException failure) {
      log.warn("요청 기록 {}건을 저장하지 못했어요: {}", rows.size(), failure.getMessage());
    }
  }

  /** 서버를 끌 때 남은 기록을 넣어요. */
  @jakarta.annotation.PreDestroy
  void flushOnShutdown() {
    flush();
  }

  /** 원본 IP를 보관 기간이 지나면 지우고, 보관 일수가 지난 기록을 지워요. 서버가 켜져 있는 시간(10시~)에 돌아요. */
  @Scheduled(cron = "0 30 11 * * *", zone = "Asia/Seoul")
  public void cleanup() {
    Instant now = clock.instant();
    int cleared =
        jdbc.update(
            "update traffic.request_logs set ip = null where ip is not null and occurred_at < ?",
            Timestamp.from(now.minus(props.rawIpDays(), ChronoUnit.DAYS)));
    int deleted =
        jdbc.update(
            "delete from traffic.request_logs where occurred_at < ?",
            Timestamp.from(now.minus(props.keepDays(), ChronoUnit.DAYS)));
    log.info("요청 기록 정리: 원본 IP 지움 {}건, 오래된 기록 지움 {}건", cleared, deleted);
  }

  /** IP 해시: 비밀 값 + 그날(한국 날짜) + IP. 날마다 달라져 오래 따라갈 수 없어요. 앞 16자만 써요. */
  String ipHash(String ip, Instant at) {
    String day = LocalDate.ofInstant(at, KST).toString();
    try {
      byte[] digest =
          MessageDigest.getInstance("SHA-256")
              .digest(
                  (props.ipSalt() + "|" + day + "|" + (ip == null ? "" : ip))
                      .getBytes(StandardCharsets.UTF_8));
      return HexFormat.of().formatHex(digest).substring(0, 16);
    } catch (NoSuchAlgorithmException impossible) {
      throw new IllegalStateException(impossible);
    }
  }

  // ---- 조회 (관리자 트래픽 화면) ----

  /** 날짜별 서버 숫자. 사람 방문자는 그날 IP 해시 수(같은 날 같은 곳에서 온 사람은 한 명). */
  public record ServerDaily(
      LocalDate date,
      long humanRequests,
      long botRequests,
      long humanVisitors,
      long signups,
      long logins,
      long loginFailures,
      long serverErrors) {}

  public List<ServerDaily> daily(Instant from, Instant to) {
    return jdbc.query(
        "select (occurred_at at time zone 'Asia/Seoul')::date d,"
            + " count(*) filter (where client = 'HUMAN' and area <> 'ADMIN') human_requests,"
            + " count(*) filter (where client <> 'HUMAN') bot_requests,"
            + " count(distinct ip_hash) filter (where client = 'HUMAN' and area <> 'ADMIN') visitors,"
            + " count(*) filter (where login_result = 'SIGNUP') signups,"
            + " count(*) filter (where login_result = 'LOGIN') logins,"
            + " count(*) filter (where login_result = 'FAILED') failures,"
            + " count(*) filter (where status >= 500) errors"
            + " from traffic.request_logs where occurred_at >= ? and occurred_at < ? group by d order by d",
        (rs, n) ->
            new ServerDaily(
                rs.getObject("d", LocalDate.class),
                rs.getLong("human_requests"),
                rs.getLong("bot_requests"),
                rs.getLong("visitors"),
                rs.getLong("signups"),
                rs.getLong("logins"),
                rs.getLong("failures"),
                rs.getLong("errors")),
        Timestamp.from(from),
        Timestamp.from(to));
  }

  public record ClientDaily(LocalDate date, String client, long requests) {}

  public List<ClientDaily> clientsDaily(Instant from, Instant to) {
    return jdbc.query(
        "select (occurred_at at time zone 'Asia/Seoul')::date d, client, count(*) n from traffic.request_logs"
            + " where occurred_at >= ? and occurred_at < ? group by d, client order by d, client",
        (rs, n) ->
            new ClientDaily(
                rs.getObject("d", LocalDate.class), rs.getString("client"), rs.getLong("n")),
        Timestamp.from(from),
        Timestamp.from(to));
  }

  /**
   * 요청이 많은 곳. 원본 IP가 남아 있으면(보관 기간 안) IP로, 지워졌으면 그날 해시로 묶어요. 화면에는 가린 IP만 보내요.
   *
   * @param peakPerMinute 1분에 가장 많이 보낸 요청 수(빠른 반복 자동화를 찾는 데 써요)
   */
  public record TopSource(
      String maskedIp,
      String key,
      String client,
      long requests,
      long peakPerMinute,
      String topPath,
      Instant firstSeen,
      Instant lastSeen) {}

  public List<TopSource> topSources(Instant from, Instant to, int limit) {
    return jdbc.query(
        "with s as (select coalesce(ip, ip_hash) k, max(ip) ip, mode() within group (order by client) client,"
            + " count(*) n, mode() within group (order by path) top_path, min(occurred_at) first_seen,"
            + " max(occurred_at) last_seen from traffic.request_logs where occurred_at >= ? and occurred_at < ?"
            + " group by k order by n desc limit ?),"
            + " m as (select coalesce(ip, ip_hash) k, max(c) peak from (select ip, ip_hash,"
            + " date_trunc('minute', occurred_at) t, count(*) c from traffic.request_logs where occurred_at >= ?"
            + " and occurred_at < ? group by ip, ip_hash, t) x group by k)"
            + " select s.*, coalesce(m.peak, 0) peak from s left join m on m.k = s.k order by s.n desc",
        (rs, n) ->
            new TopSource(
                RequestClassifier.maskIp(rs.getString("ip")),
                rs.getString("ip") == null ? rs.getString("k") : null,
                rs.getString("client"),
                rs.getLong("n"),
                rs.getLong("peak"),
                rs.getString("top_path"),
                rs.getTimestamp("first_seen").toInstant(),
                rs.getTimestamp("last_seen").toInstant()),
        Timestamp.from(from),
        Timestamp.from(to),
        limit,
        Timestamp.from(from),
        Timestamp.from(to));
  }

  public record PathCount(String path, long requests, long humanRequests, long botRequests) {}

  /** 사람이 아닌 요청이 많이 온 경로. */
  public List<PathCount> topBotPaths(Instant from, Instant to, int limit) {
    return jdbc.query(
        "select path, count(*) n, count(*) filter (where client = 'HUMAN') h,"
            + " count(*) filter (where client <> 'HUMAN') b from traffic.request_logs"
            + " where occurred_at >= ? and occurred_at < ? group by path"
            + " order by b desc, n desc limit ?",
        (rs, n) ->
            new PathCount(rs.getString("path"), rs.getLong("n"), rs.getLong("h"), rs.getLong("b")),
        Timestamp.from(from),
        Timestamp.from(to),
        limit);
  }

  public record StatusCount(String group, long requests) {}

  /** 거절·오류 응답 수: 401(로그인 필요)·403(권한 없음)·404·429(요청 제한)·5xx. */
  public List<StatusCount> statuses(Instant from, Instant to) {
    return jdbc.query(
        "select case when status >= 500 then '5xx' else status::text end g, count(*) n"
            + " from traffic.request_logs where occurred_at >= ? and occurred_at < ?"
            + " and (status in (401, 403, 404, 429) or status >= 500) group by g order by g",
        (rs, n) -> new StatusCount(rs.getString("g"), rs.getLong("n")),
        Timestamp.from(from),
        Timestamp.from(to));
  }

  public record Access(
      Instant at, String method, String path, Integer status, String maskedIp, String client) {}

  /** 최근 관리자 API 요청(누가 했는지는 저장하지 않아요. 시각·경로·결과·가린 IP). */
  public List<Access> adminAccess(Instant from, Instant to, int limit) {
    return access("area = 'ADMIN'", from, to, limit);
  }

  /** 최근 로그인 실패. */
  public List<Access> loginFailures(Instant from, Instant to, int limit) {
    return access("login_result = 'FAILED'", from, to, limit);
  }

  private List<Access> access(String where, Instant from, Instant to, int limit) {
    return jdbc.query(
        "select occurred_at, method, path, status, ip, client from traffic.request_logs where "
            + where
            + " and occurred_at >= ? and occurred_at < ? order by occurred_at desc limit ?",
        (rs, n) ->
            new Access(
                rs.getTimestamp("occurred_at").toInstant(),
                rs.getString("method"),
                rs.getString("path"),
                rs.getObject("status", Integer.class),
                RequestClassifier.maskIp(rs.getString("ip")),
                rs.getString("client")),
        Timestamp.from(from),
        Timestamp.from(to),
        limit);
  }
}
