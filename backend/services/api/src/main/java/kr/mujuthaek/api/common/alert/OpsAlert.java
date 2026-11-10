package kr.mujuthaek.api.common.alert;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

/**
 * 운영자가 바로 알아야 하는 일을 슬랙으로 보내요 (처리하지 못한 오류, 실패 큐로 간 메시지, area 적재 실패·멈춤, 다른 서비스 연결 실패).
 *
 * <ul>
 *   <li>같은 종류(kind)는 {@code quiet}(기본 10분) 안에 한 번만 보내고, 그동안 생긴 횟수는 다음 알림에 붙여요
 *   <li>보내기는 따로 도는 가상 스레드에서 해서 요청·수신 처리를 막지 않아요. 실패해도 경고 로그 한 줄로 끝나요
 *   <li>웹훅 주소가 없으면(로컬) 보내지 않아요
 * </ul>
 *
 * <p>내용에 개인 정보·비밀 값을 넣지 마세요 (경로·오류 종류·건수만).
 */
@Component
@EnableConfigurationProperties(OpsAlertProperties.class)
public class OpsAlert {

  /** 웹훅 주소를 읽는 환경 변수 이름 (추출 서비스와 같은 키). */
  public static final String WEBHOOK_ENV = "SLACK_WEBHOOK_URL";

  private static final Logger log = LoggerFactory.getLogger(OpsAlert.class);
  private static final Duration TIMEOUT = Duration.ofSeconds(5);
  private static final int MAX_TEXT = 2500;

  private final OpsAlertProperties properties;
  private final JsonMapper json;
  private final Clock clock;
  private final HttpClient http;
  private final Map<String, Window> windows = new ConcurrentHashMap<>();

  @Autowired
  public OpsAlert(OpsAlertProperties properties, JsonMapper json) {
    this(properties, json, Clock.systemUTC());
  }

  OpsAlert(OpsAlertProperties properties, JsonMapper json, Clock clock) {
    this.properties = properties;
    this.json = json;
    this.clock = clock;
    this.http = HttpClient.newBuilder().connectTimeout(TIMEOUT).build();
  }

  /** 이 환경에서 알리지 않을 오류 코드인지 (mujuthaek.ops-alert.ignore-codes). */
  public boolean ignores(String code) {
    return properties.ignores(code);
  }

  /** 종류별로 묶는 창: 마지막으로 보낸 시각과 그 뒤 못 보낸 횟수. */
  private record Window(Instant sentAt, int suppressed) {}

  /**
   * @param kind 묶는 단위 (예: api.unhandled:/api/v1/notices). 같은 kind는 quiet 동안 한 번만 보내요
   * @param title 한 줄 요약
   * @param detail 자세한 내용 (없으면 null). 길면 잘라요
   */
  public void send(String kind, String title, String detail) {
    String text = take(kind, title, detail);
    if (text == null) {
      return;
    }
    if (!properties.enabled()) {
      log.debug("슬랙 알림 주소가 없어 보내지 않아요: {}", title);
      return;
    }
    Thread.ofVirtual().name("ops-alert").start(() -> post(text));
  }

  /** 보낼 차례면 메시지를, 아직 조용히 할 때면 null을 돌려줘요 (횟수만 세요). */
  String take(String kind, String title, String detail) {
    Instant now = clock.instant();
    int[] skipped = {0};
    boolean[] due = {false};
    windows.compute(
        kind,
        (k, w) -> {
          if (w == null || !now.isBefore(w.sentAt().plus(properties.quiet()))) {
            due[0] = true;
            skipped[0] = w == null ? 0 : w.suppressed();
            return new Window(now, 0);
          }
          return new Window(w.sentAt(), w.suppressed() + 1);
        });
    if (!due[0]) {
      return null;
    }
    StringBuilder text =
        new StringBuilder("[").append(properties.environment()).append(" api] ").append(title);
    if (skipped[0] > 0) {
      text.append(" (지난 알림 뒤 같은 일 ").append(skipped[0]).append("번 더)");
    }
    if (detail != null && !detail.isBlank()) {
      text.append("\n```").append(detail.strip()).append("```");
    }
    return text.length() > MAX_TEXT ? text.substring(0, MAX_TEXT) + "…```" : text.toString();
  }

  private void post(String text) {
    try {
      HttpRequest request =
          HttpRequest.newBuilder(URI.create(properties.webhookUrl()))
              .timeout(TIMEOUT)
              .header("Content-Type", "application/json")
              .POST(
                  HttpRequest.BodyPublishers.ofString(
                      json.writeValueAsString(Map.of("text", text))))
              .build();
      HttpResponse<Void> response = http.send(request, HttpResponse.BodyHandlers.discarding());
      if (response.statusCode() >= 300) {
        log.warn("슬랙 알림을 보내지 못했어요 (status {})", response.statusCode());
      }
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
    } catch (Exception e) {
      // 웹훅 주소는 비밀이라 예외 메시지(주소가 들어갈 수 있음) 대신 종류만 남겨요
      log.warn("슬랙 알림을 보내지 못했어요: {}", e.getClass().getSimpleName());
    }
  }
}
