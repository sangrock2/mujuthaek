package kr.mujuthaek.api.traffic.controller;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import kr.mujuthaek.api.TestDatabase;
import kr.mujuthaek.api.traffic.TrafficProperties;
import kr.mujuthaek.api.traffic.dto.TrafficPageRequest;
import kr.mujuthaek.api.traffic.log.RequestLogStore;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

/** 프론트 서버가 넘긴 화면 요청: 비밀 값이 맞을 때만 「화면」 요청으로 쌓고, 봇 숫자에 들어가요. */
class InternalTrafficControllerTest {

  private static final Instant NOW = Instant.parse("2026-10-26T03:00:00Z");
  private static final String GOOGLEBOT =
      "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)";
  private final Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
  private final JdbcTemplate jdbc = new JdbcTemplate(TestDatabase.dataSource());

  private RequestLogStore store;

  private InternalTrafficController controller(String token) {
    var props =
        new TrafficProperties(
            "salt",
            14,
            90,
            token,
            new TrafficProperties.Ga("", "", Duration.ofHours(1), Duration.ofSeconds(5)));
    store = new RequestLogStore(jdbc, props, clock);
    return new InternalTrafficController(props, store, clock);
  }

  @BeforeEach
  void clean() {
    jdbc.update("truncate traffic.request_logs");
  }

  @Test
  void 비밀_값을_안_넣었으면_받지_않는다() {
    var res = controller("").page("x", new TrafficPageRequest("/", GOOGLEBOT, "66.249.66.1"));
    assertThat(res.getStatusCode().value()).isEqualTo(404);
  }

  @Test
  void 비밀_값이_틀리면_받지_않는다() {
    var c = controller("secret");
    assertThat(
            c.page("wrong", new TrafficPageRequest("/", GOOGLEBOT, "66.249.66.1"))
                .getStatusCode()
                .value())
        .isEqualTo(403);
    assertThat(
            c.page(null, new TrafficPageRequest("/", GOOGLEBOT, "66.249.66.1"))
                .getStatusCode()
                .value())
        .isEqualTo(403);
    store.flush();
    assertThat(jdbc.queryForObject("select count(*) from traffic.request_logs", Long.class))
        .isZero();
  }

  @Test
  void 화면_요청을_봇_숫자에_넣는다() {
    var c = controller("secret");
    for (int i = 0; i < 3; i++) {
      var res =
          c.page(
              "secret",
              new TrafficPageRequest(
                  "/notices/01a1723f-ee21-7000-a557-7365aad3daa7?pdf=1", GOOGLEBOT, "66.249.66.1"));
      assertThat(res.getStatusCode().value()).isEqualTo(202);
    }
    c.page(
        "secret",
        new TrafficPageRequest("/homes", "Mozilla/5.0 Chrome/130.0", "not an ip<script>"));
    store.flush();

    Instant from = NOW.minus(Duration.ofDays(1));
    Instant to = NOW.plusSeconds(1);
    assertThat(store.daily(from, to))
        .singleElement()
        .satisfies(
            d -> {
              assertThat(d.botRequests()).isEqualTo(3);
              assertThat(d.serverErrors()).isZero();
            });
    var path = store.topBotPaths(from, to, 5).getFirst();
    assertThat(path.path()).isEqualTo("/notices/{id}"); // 쿼리는 빼고 ID는 묶어요
    assertThat(path.botRequests()).isEqualTo(3);
    assertThat(store.statuses(from, to)).isEmpty(); // 응답 코드를 모르는 화면 요청은 오류로 세지 않아요
    assertThat(
            jdbc.queryForList(
                "select area || ',' || coalesce(status::text, '-') || ',' || coalesce(ip, '-')"
                    + " from traffic.request_logs where client = 'HUMAN'",
                String.class))
        .containsExactly("PAGE,-,-"); // 이상한 IP 값은 버려요
  }
}
