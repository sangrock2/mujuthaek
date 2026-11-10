package kr.mujuthaek.api.common.alert;

import static org.assertj.core.api.Assertions.assertThat;

import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

class OpsAlertTest {

  private final JsonMapper json = JsonMapper.builder().build();

  @Test
  void sameKindIsSentOncePerQuietWindow_andTheSkippedCountRidesOnTheNextOne() {
    var clock = new MutableClock();
    var alert =
        new OpsAlert(
            new OpsAlertProperties(null, "prod", Duration.ofMinutes(10), null), json, clock);

    assertThat(alert.take("a", "검수 API 연결 실패", null)).isEqualTo("[prod api] 검수 API 연결 실패");
    assertThat(alert.take("a", "검수 API 연결 실패", null)).isNull();
    assertThat(alert.take("a", "검수 API 연결 실패", null)).isNull();
    assertThat(alert.take("b", "다른 종류", null)).isNotNull();

    clock.now = clock.now.plus(Duration.ofMinutes(10));
    assertThat(alert.take("a", "검수 API 연결 실패", "ConnectException"))
        .isEqualTo("[prod api] 검수 API 연결 실패 (지난 알림 뒤 같은 일 2번 더)\n```ConnectException```");
  }

  @Test
  void ignoreCodesComeFromConfig() {
    var properties =
        new OpsAlertProperties(null, "dev", null, java.util.Set.of("NOTICE_COLLECTOR_UNAVAILABLE"));

    assertThat(properties.ignores("NOTICE_COLLECTOR_UNAVAILABLE")).isTrue();
    assertThat(properties.ignores("NOTICE_REVIEW_UNAVAILABLE")).isFalse();
    assertThat(new OpsAlertProperties(null, null, null, null).ignoreCodes()).isEmpty();
  }

  @Test
  void postsTheTextToTheWebhook() throws Exception {
    BlockingQueue<String> bodies = new ArrayBlockingQueue<>(1);
    HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
    server.createContext(
        "/hook",
        exchange -> {
          bodies.add(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
          exchange.sendResponseHeaders(200, -1);
          exchange.close();
        });
    server.start();
    try {
      String url = "http://127.0.0.1:" + server.getAddress().getPort() + "/hook";
      var alert = new OpsAlert(new OpsAlertProperties(url, "dev", null, null), json);

      alert.send("area.load.failed:STORES", "area 적재 실패: STORES 강원", "칸이 없어요");

      assertThat(bodies.poll(5, TimeUnit.SECONDS))
          .isEqualTo(
              json.writeValueAsString(
                  java.util.Map.of("text", "[dev api] area 적재 실패: STORES 강원\n```칸이 없어요```")));
    } finally {
      server.stop(0);
    }
  }

  @Test
  void withoutWebhook_nothingIsSent_andPropertiesHideTheUrl() {
    var properties = new OpsAlertProperties("", null, null, null);
    assertThat(properties.enabled()).isFalse();
    assertThat(properties.environment()).isEqualTo("local");
    assertThat(
            new OpsAlertProperties("https://hooks.slack.com/services/x", "prod", null, null)
                .toString())
        .doesNotContain("hooks.slack.com");
    new OpsAlert(properties, json).send("k", "t", null);
  }

  private static final class MutableClock extends Clock {
    Instant now = Instant.parse("2026-10-29T00:00:00Z");

    @Override
    public java.time.ZoneId getZone() {
      return ZoneOffset.UTC;
    }

    @Override
    public Clock withZone(java.time.ZoneId zone) {
      return this;
    }

    @Override
    public Instant instant() {
      return now;
    }
  }
}
