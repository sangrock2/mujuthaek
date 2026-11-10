package kr.mujuthaek.api.traffic;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.servlet.http.HttpServletResponse;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import kr.mujuthaek.api.TestDatabase;
import kr.mujuthaek.api.traffic.log.RequestClassifier.Area;
import kr.mujuthaek.api.traffic.log.RequestClassifier.Client;
import kr.mujuthaek.api.traffic.log.RequestLogFilter;
import kr.mujuthaek.api.traffic.log.RequestLogStore;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.web.filter.ForwardedHeaderFilter;

/** 요청 기록: 필터가 남긴 기록을 모아 넣고, 가입·로그인 실패·봇·관리자 접근을 세고, 원본 IP는 보관 기간 뒤 지워요. */
class RequestLogStoreTest {

  private static final String CHROME =
      "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/130.0 Safari/537.36";
  private static final Instant NOW = Instant.parse("2026-10-26T03:00:00Z");
  private final Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
  private final JdbcTemplate jdbc = new JdbcTemplate(TestDatabase.dataSource());
  private final TrafficProperties props =
      new TrafficProperties(
          "salt",
          14,
          90,
          "ingest-token",
          new TrafficProperties.Ga("", "", Duration.ofHours(1), Duration.ofSeconds(5)));
  private final RequestLogStore store = new RequestLogStore(jdbc, props, clock);
  private final RequestLogFilter filter = new RequestLogFilter(store, clock);

  @BeforeEach
  void clean() {
    jdbc.update("truncate traffic.request_logs");
  }

  private void request(
      String method, String path, String ua, String ip, int status, String location)
      throws Exception {
    var request = new MockHttpServletRequest(method, path);
    if (ua != null) request.addHeader("User-Agent", ua);
    request.setRemoteAddr(ip);
    var response = new MockHttpServletResponse();
    filter.doFilter(
        request,
        response,
        new MockFilterChain() {
          @Override
          public void doFilter(
              jakarta.servlet.ServletRequest req, jakarta.servlet.ServletResponse res) {
            ((HttpServletResponse) res).setStatus(status);
            if (location != null) ((HttpServletResponse) res).setHeader("Location", location);
          }
        });
  }

  @Test
  void 가입_로그인_실패_봇_관리자_접근을_센다() throws Exception {
    request("GET", "/api/v1/notices", CHROME, "203.0.113.5", 200, null);
    request(
        "GET",
        "/login/oauth2/code/kakao",
        CHROME,
        "203.0.113.5",
        302,
        "http://f/auth/callback?new=1");
    request(
        "GET",
        "/login/oauth2/code/kakao",
        CHROME,
        "203.0.113.9",
        302,
        "http://f/login?error=social");
    for (int i = 0; i < 3; i++) {
      request(
          "GET",
          "/api/v1/notices/01a1723f-ee21-7000-a557-7365aad3daa7",
          "curl/8.4",
          "198.51.100.7",
          200,
          null);
    }
    request("GET", "/api/admin/reviews", CHROME, "203.0.113.5", 403, null);
    request("OPTIONS", "/api/v1/notices", CHROME, "203.0.113.5", 200, null); // CORS 사전 요청은 안 셈
    request("GET", "/actuator/health", null, "10.0.0.1", 200, null); // 상태 확인은 안 셈
    store.flush();

    Instant from = NOW.minus(Duration.ofDays(1));
    Instant to = NOW.plusSeconds(1);
    var day = store.daily(from, to);
    assertThat(day)
        .singleElement()
        .satisfies(
            d -> {
              assertThat(d.date()).isEqualTo(LocalDate.of(2026, 10, 26));
              assertThat(d.signups()).isEqualTo(1);
              assertThat(d.loginFailures()).isEqualTo(1);
              assertThat(d.botRequests()).isEqualTo(3);
              assertThat(d.humanRequests()).isEqualTo(3); // 관리자 요청은 사람 방문에서 빼요
              assertThat(d.humanVisitors()).isEqualTo(2);
            });
    var top = store.topSources(from, to, 5).getFirst();
    assertThat(top.maskedIp()).isEqualTo("198.51.100.x");
    assertThat(top.client()).isEqualTo("TOOL");
    assertThat(top.requests()).isEqualTo(3);
    assertThat(top.peakPerMinute()).isEqualTo(3);
    assertThat(top.topPath()).isEqualTo("/api/v1/notices/{id}");
    assertThat(store.statuses(from, to))
        .anySatisfy(
            s -> {
              assertThat(s.group()).isEqualTo("403");
              assertThat(s.requests()).isEqualTo(1);
            });
    assertThat(store.adminAccess(from, to, 10))
        .singleElement()
        .satisfies(
            a -> {
              assertThat(a.path()).isEqualTo("/api/admin/reviews");
              assertThat(a.maskedIp()).isEqualTo("203.0.113.x");
            });
    assertThat(store.loginFailures(from, to, 10))
        .singleElement()
        .satisfies(a -> assertThat(a.maskedIp()).isEqualTo("203.0.113.x"));
    assertThat(store.topBotPaths(from, to, 5).getFirst().path()).isEqualTo("/api/v1/notices/{id}");
    // 원본 IP 말고 저장하는 값에는 쿼리·회원 정보가 없어요
    assertThat(
            jdbc.queryForObject(
                "select count(*) from traffic.request_logs where path like '%?%'", Long.class))
        .isZero();
  }

  @Test
  void 전달_헤더로_주소_앞을_바꿔도_기록에서_빠지지_않는다() throws Exception {
    // 2026-11-10 코드 검토: X-Forwarded-Prefix: /actuator를 붙이면 요청 주소가 /actuator/…로 바뀌어 상태 확인처럼 기록에서 빠졌음
    var request = new MockHttpServletRequest("GET", "/api/admin/reviews");
    request.addHeader("X-Forwarded-Prefix", "/actuator");
    request.addHeader("User-Agent", CHROME);
    request.setRemoteAddr("203.0.113.5");
    new ForwardedHeaderFilter()
        .doFilter(
            request,
            new MockHttpServletResponse(),
            (req, res) -> filter.doFilter(req, res, new MockFilterChain()));
    store.flush();

    assertThat(jdbc.queryForList("select path from traffic.request_logs", String.class))
        .containsExactly("/api/admin/reviews");
  }

  @Test
  void 원본_IP는_보관_기간_뒤_지우고_오래된_기록은_지운다() {
    store.add(entry(NOW.minus(Duration.ofDays(20)), "203.0.113.5"));
    store.add(entry(NOW.minus(Duration.ofDays(100)), "203.0.113.6"));
    store.add(entry(NOW.minus(Duration.ofDays(1)), "203.0.113.7"));
    store.flush();

    store.cleanup();

    assertThat(
            jdbc.queryForList(
                "select ip from traffic.request_logs order by occurred_at", String.class))
        .containsExactly(null, "203.0.113.7");
  }

  @Test
  void IP_해시는_날마다_달라진다() {
    store.add(entry(NOW.minus(Duration.ofDays(1)), "203.0.113.5"));
    store.add(entry(NOW, "203.0.113.5"));
    store.flush();
    assertThat(
            jdbc.queryForObject(
                "select count(distinct ip_hash) from traffic.request_logs", Long.class))
        .isEqualTo(2);
  }

  private static RequestLogStore.Entry entry(Instant at, String ip) {
    return new RequestLogStore.Entry(
        at, "GET", "/api/v1/notices", 200, 5, Client.HUMAN, "x", ip, Area.API, null);
  }
}
