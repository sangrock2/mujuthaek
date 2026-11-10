package kr.mujuthaek.api.traffic.ga;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServerError;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyPairGenerator;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.Base64;
import kr.mujuthaek.api.TestDatabase;
import kr.mujuthaek.api.traffic.TrafficProperties;
import kr.mujuthaek.api.traffic.log.RequestLogStore;
import kr.mujuthaek.api.traffic.service.TrafficService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import tools.jackson.databind.json.JsonMapper;

/** 트래픽 서비스: GA 보고서를 화면 숫자로 바꾸고, 같은 기간은 한 시간 안에 다시 묻지 않고, GA가 없거나 실패해도 서버 숫자는 줘요. */
class TrafficServiceTest {

  private static final Instant NOW = Instant.parse("2026-10-26T03:00:00Z");
  private static final String ROW =
      "{\"dimensionValues\":[{\"value\":\"%s\"}],\"metricValues\":[%s]}";

  @TempDir Path dir;
  private final Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
  private final JdbcTemplate jdbc = new JdbcTemplate(TestDatabase.dataSource());

  private TrafficProperties props(String propertyId, String keyFile) {
    return new TrafficProperties(
        "salt",
        14,
        90,
        "",
        new TrafficProperties.Ga(propertyId, keyFile, Duration.ofHours(1), Duration.ofSeconds(5)));
  }

  private static String row(String dim, long... values) {
    var m = new StringBuilder();
    for (long v : values)
      m.append(m.isEmpty() ? "" : ",").append("{\"value\":\"").append(v).append("\"}");
    return ROW.formatted(dim, m);
  }

  private static String report(String... rows) {
    return "{\"rows\":[" + String.join(",", rows) + "]}";
  }

  @Test
  void GA_보고서를_화면_숫자로_바꾸고_한_시간_안에는_다시_묻지_않는다() throws Exception {
    var pair = KeyPairGenerator.getInstance("RSA");
    pair.initialize(2048);
    var key = JsonMapper.builder().build().createObjectNode();
    key.put("client_email", "a@test.iam.gserviceaccount.com");
    key.put(
        "private_key",
        "-----BEGIN PRIVATE KEY-----\n"
            + Base64.getEncoder().encodeToString(pair.generateKeyPair().getPrivate().getEncoded())
            + "\n-----END PRIVATE KEY-----\n");
    key.put("token_uri", "http://token.test/token");
    Path file = dir.resolve("key.json");
    Files.writeString(file, key.toString());
    var props = props("123", file.toString());
    RestClient.Builder builder = RestClient.builder();
    MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
    var ga = new GaDataClient(props.ga(), builder, clock, "http://ga.test");
    var service = new TrafficService(ga, new RequestLogStore(jdbc, props, clock), props, clock);

    server
        .expect(requestTo("http://token.test/token"))
        .andRespond(
            withSuccess(
                "{\"access_token\":\"t\",\"expires_in\":3600}", MediaType.APPLICATION_JSON));
    server
        .expect(requestTo("http://ga.test/properties/123:batchRunReports"))
        .andRespond(
            withSuccess(
                "{\"reports\":["
                    + report(row("20261025", 10, 4, 12, 30), row("20261026", 7, 2, 8, 20))
                    + ","
                    + report(row("Organic Search", 9, 6), row("Direct", 5, 4))
                    + ","
                    + report(row("naver", 6, 4))
                    + ","
                    + report()
                    + ","
                    + report(row("/", 11, 7))
                    + "]}",
                MediaType.APPLICATION_JSON));
    server
        .expect(requestTo("http://ga.test/properties/123:batchRunReports"))
        .andRespond(
            withSuccess(
                "{\"reports\":["
                    + report(row("/notices/{id}", 40, 9))
                    + ","
                    + report(row("mobile", 12))
                    + ","
                    + report(row("Chrome", 10))
                    + ","
                    + report(row("Seoul", 8))
                    + ","
                    + report(row("session_start", 20, 15), row("judgment_run", 6, 4))
                    + "]}",
                MediaType.APPLICATION_JSON));
    server
        .expect(requestTo("http://ga.test/properties/123:batchRunReports"))
        .andRespond(
            withSuccess(
                "{\"reports\":["
                    + report(
                        row("/notices/a", 10, 3),
                        row("/notices/b", 5, 2),
                        row("/notices/a/units", 2, 1),
                        row("/notices/", 9, 9))
                    + "]}",
                MediaType.APPLICATION_JSON));

    var first = service.traffic(7);
    var again = service.traffic(7); // 한 시간 안: GA를 다시 부르지 않아요(부르면 가짜 서버가 실패시켜요)
    server.verify();

    var g = first.ga();
    assertThat(g.connected()).isTrue();
    assertThat(g.daily())
        .hasSize(2)
        .first()
        .satisfies(
            d -> {
              assertThat(d.date()).isEqualTo(LocalDate.of(2026, 10, 25));
              assertThat(d.activeUsers()).isEqualTo(10);
              assertThat(d.pageViews()).isEqualTo(30);
            });
    assertThat(g.channels())
        .extracting(i -> i.name() + ":" + i.value() + "/" + i.users())
        .containsExactly("Organic Search:9/6", "Direct:5/4");
    assertThat(g.devices())
        .singleElement()
        .satisfies(
            i -> {
              assertThat(i.value()).isEqualTo(12);
              assertThat(i.users()).isEqualTo(12); // 기기는 활성 사용자가 주 값
            });
    assertThat(g.funnel())
        .extracting(f -> f.label() + "=" + f.count())
        .containsExactly("방문=20", "조건 입력 완료=0", "판정 실행=6", "원문 보기=0", "관심 등록=0");
    // 공고 상세의 하위 경로는 같은 공고로 합치고, ID 없는 /notices/는 빼요
    assertThat(g.popularNotices())
        .extracting(n -> n.noticeId() + ":" + n.views() + "/" + n.users())
        .containsExactly("a:12/4", "b:5/2");
    assertThat(again.ga()).isSameAs(g);
  }

  @Test
  void 지금_접속자는_최근_30분_5분_기기별을_묻고_30초_안에는_다시_묻지_않는다() throws Exception {
    var pair = KeyPairGenerator.getInstance("RSA");
    pair.initialize(2048);
    var key = JsonMapper.builder().build().createObjectNode();
    key.put("client_email", "a@test.iam.gserviceaccount.com");
    key.put(
        "private_key",
        "-----BEGIN PRIVATE KEY-----\n"
            + Base64.getEncoder().encodeToString(pair.generateKeyPair().getPrivate().getEncoded())
            + "\n-----END PRIVATE KEY-----\n");
    key.put("token_uri", "http://token.test/token");
    Path file = dir.resolve("key.json");
    Files.writeString(file, key.toString());
    var props = props("123", file.toString());
    RestClient.Builder builder = RestClient.builder();
    MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
    var ga = new GaDataClient(props.ga(), builder, clock, "http://ga.test");
    var service = new TrafficService(ga, new RequestLogStore(jdbc, props, clock), props, clock);

    server
        .expect(requestTo("http://token.test/token"))
        .andRespond(
            withSuccess(
                "{\"access_token\":\"t\",\"expires_in\":3600}", MediaType.APPLICATION_JSON));
    server
        .expect(requestTo("http://ga.test/properties/123:runRealtimeReport"))
        .andRespond(
            withSuccess(
                report("{\"metricValues\":[{\"value\":\"7\"}]}"), MediaType.APPLICATION_JSON));
    server
        .expect(requestTo("http://ga.test/properties/123:runRealtimeReport"))
        .andExpect(content().string(org.hamcrest.Matchers.containsString("\"startMinutesAgo\":4")))
        .andRespond(
            withSuccess(
                report("{\"metricValues\":[{\"value\":\"2\"}]}"), MediaType.APPLICATION_JSON));
    server
        .expect(requestTo("http://ga.test/properties/123:runRealtimeReport"))
        .andRespond(
            withSuccess(report(row("desktop", 2), row("mobile", 5)), MediaType.APPLICATION_JSON));

    var now = service.realtime();
    var again = service.realtime(); // 30초 안: 다시 묻지 않아요
    server.verify();

    assertThat(now.connected()).isTrue();
    assertThat(now.last30Minutes()).isEqualTo(7);
    assertThat(now.last5Minutes()).isEqualTo(2);
    assertThat(now.devices())
        .extracting(i -> i.name() + ":" + i.value())
        .containsExactly("mobile:5", "desktop:2");
    assertThat(again).isSameAs(now);
  }

  @Test
  void GA가_없거나_실패해도_서버_숫자는_준다() {
    var off = props("", "");
    var service =
        new TrafficService(
            new GaDataClient(off.ga(), RestClient.builder(), clock, "http://ga.test"),
            new RequestLogStore(jdbc, off, clock),
            off,
            clock);
    var result = service.traffic(7);
    assertThat(result.ga().connected()).isFalse();
    assertThat(result.ga().error()).contains("연결되지 않았어요");
    assertThat(result.server()).isNotNull();

    var broken = props("123", dir.resolve("없는-키.json").toString());
    RestClient.Builder builder = RestClient.builder();
    MockRestServiceServer.bindTo(builder)
        .build()
        .expect(requestTo("http://ga.test"))
        .andRespond(withServerError());
    var failing =
        new TrafficService(
            new GaDataClient(broken.ga(), builder, clock, "http://ga.test"),
            new RequestLogStore(jdbc, broken, clock),
            broken,
            clock);
    assertThat(failing.traffic(7).ga().error()).contains("가져오지 못했어요");
  }
}
