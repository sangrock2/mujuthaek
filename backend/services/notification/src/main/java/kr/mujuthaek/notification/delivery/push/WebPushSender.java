package kr.mujuthaek.notification.delivery.push;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.security.GeneralSecurityException;
import java.time.Clock;
import java.time.Duration;
import java.util.Optional;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * 푸시 서비스(Google·Mozilla·Apple·Microsoft)로 보내요 (notification.push.provider=webpush). 내용은 그 기기만 열 수
 * 있게 암호화하고({@link WebPushCrypto}), 우리 서비스가 보냈다는 서명(VAPID)을 붙여요. 브라우저마다 다른 코드는 없어요.
 */
@Component
@ConditionalOnProperty(name = "notification.push.provider", havingValue = "webpush")
class WebPushSender implements PushSender {

  /** 다시 보낼 때까지 기다리라는 시간의 상한 (이상한 값이 와도 하루 넘게 미루지 않아요) */
  static final Duration MAX_RETRY_AFTER = Duration.ofDays(1);

  private final Vapid vapid;
  private final HttpClient http;
  private final Duration timeout;
  private final Clock clock;

  @Autowired
  WebPushSender(PushProperties properties, Clock clock) {
    this(
        new Vapid(
            properties.vapidPublicKey(), properties.vapidPrivateKey(), properties.vapidSubject()),
        HttpClient.newBuilder()
            .connectTimeout(properties.timeout())
            .followRedirects(HttpClient.Redirect.NEVER) // 푸시 서비스 밖으로 가지 않게
            .build(),
        properties.timeout(),
        clock);
  }

  WebPushSender(Vapid vapid, HttpClient http, Duration timeout, Clock clock) {
    this.vapid = vapid;
    this.http = http;
    this.timeout = timeout;
    this.clock = clock;
  }

  @Override
  public PushResponse send(PushMessage message) throws IOException {
    URI endpoint = URI.create(message.device().endpoint());
    byte[] body;
    String authorization;
    try {
      body =
          WebPushCrypto.encrypt(
              message.payload(), message.device().p256dh(), message.device().auth());
      authorization = vapid.authorization(endpoint, clock.instant());
    } catch (GeneralSecurityException | IllegalArgumentException e) {
      // 기기 키가 곡선 위의 점이 아니거나 base64url이 아니에요. 다시 보내도 같아서 400처럼 다뤄요
      return new PushResponse(400, null);
    }
    HttpRequest request =
        HttpRequest.newBuilder(endpoint)
            .timeout(timeout)
            .header("TTL", Long.toString(message.ttl().toSeconds()))
            .header("Urgency", message.urgency())
            .header("Content-Encoding", "aes128gcm")
            .header("Content-Type", "application/octet-stream")
            .header("Authorization", authorization)
            .POST(HttpRequest.BodyPublishers.ofByteArray(body))
            .build();
    try {
      HttpResponse<Void> response = http.send(request, HttpResponse.BodyHandlers.discarding());
      return new PushResponse(
          response.statusCode(),
          response
              .headers()
              .firstValue("Retry-After")
              .flatMap(WebPushSender::seconds)
              .orElse(null));
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new IOException("보내는 중에 멈췄어요", e);
    }
  }

  /** Retry-After의 초 값. 날짜 모양이거나 이상하면 비어 있어요 (그러면 정한 재시도 간격을 써요) */
  static Optional<Duration> seconds(String value) {
    try {
      long seconds = Long.parseLong(value.strip());
      if (seconds < 0) {
        return Optional.empty();
      }
      Duration d = Duration.ofSeconds(seconds);
      return Optional.of(d.compareTo(MAX_RETRY_AFTER) > 0 ? MAX_RETRY_AFTER : d);
    } catch (NumberFormatException e) {
      return Optional.empty();
    }
  }
}
