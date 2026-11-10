package kr.mujuthaek.notification.delivery.push;

import static org.assertj.core.api.Assertions.assertThat;

import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.interfaces.ECPublicKey;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;
import kr.mujuthaek.notification.notification.NotificationRequest.PushDevice;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * 실제 HTTP로 보내 봐요 (가짜 푸시 서비스를 이 컴퓨터에 띄움). 헤더가 표준대로인지, 기기 키로 내용이 풀리는지, 답을 그대로 돌려주는지. 받을 곳 허용 목록은
 * PushChannel이 보고, 이 클래스는 받은 주소로 보내기만 해요.
 */
class WebPushSenderTest {

  HttpServer server;
  final AtomicReference<byte[]> body = new AtomicReference<>();
  final Map<String, String> headers = new ConcurrentHashMap<>();
  final AtomicReference<Integer> status = new AtomicReference<>(201);
  final AtomicReference<String> retryAfter = new AtomicReference<>();

  @BeforeEach
  void start() throws Exception {
    server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
    server.createContext(
        "/push",
        exchange -> {
          body.set(exchange.getRequestBody().readAllBytes());
          exchange
              .getRequestHeaders()
              .forEach((k, v) -> headers.put(k.toLowerCase(), v.getFirst()));
          if (retryAfter.get() != null) {
            exchange.getResponseHeaders().add("Retry-After", retryAfter.get());
          }
          exchange.sendResponseHeaders(status.get(), -1);
          exchange.close();
        });
    server.start();
  }

  @AfterEach
  void stop() {
    server.stop(0);
  }

  @Test
  void postsAnEncryptedBodyTheDeviceCanOpen() throws Exception {
    KeyPair vapidKeys = VapidTest.keyPair();
    KeyPair device = VapidTest.keyPair();
    byte[] auth = new byte[16];
    auth[0] = 7;
    WebPushSender sender = sender(vapidKeys);
    byte[] payload = "{\"v\":1,\"title\":\"정정: 서리풀\"}".getBytes(StandardCharsets.UTF_8);

    PushResponse response =
        sender.send(
            new PushMessage(
                new PushDevice(
                    endpoint(),
                    WebPushCryptoTest.b64(
                        WebPushCrypto.encodePublic((ECPublicKey) device.getPublic())),
                    WebPushCryptoTest.b64(auth)),
                payload,
                Duration.ofHours(12),
                "high"));

    assertThat(response.status()).isEqualTo(201);
    assertThat(headers)
        .containsEntry("ttl", "43200")
        .containsEntry("urgency", "high")
        .containsEntry("content-encoding", "aes128gcm")
        .containsEntry("content-type", "application/octet-stream");
    assertThat(headers.get("authorization"))
        .startsWith("vapid t=")
        .endsWith(", k=" + VapidTest.publicKey(vapidKeys));
    assertThat(WebPushCryptoTest.decrypt(body.get(), device, auth)).isEqualTo(payload);
  }

  @Test
  void returnsTheStatusAndRetryAfterAsIs() throws Exception {
    status.set(429);
    retryAfter.set("120");

    PushResponse response = sender(VapidTest.keyPair()).send(message(validDevice()));

    assertThat(response.status()).isEqualTo(429);
    assertThat(response.retryAfter()).isEqualTo(Duration.ofMinutes(2));
  }

  @Test
  void brokenDeviceKeysAreTreatedLikeABadRequestWithoutCalling() throws Exception {
    PushResponse response =
        sender(VapidTest.keyPair())
            .send(message(new PushDevice(endpoint(), "not-a-key", "AAAAAAAAAAAAAAAAAAAAAA")));

    assertThat(response.status()).isEqualTo(400);
    assertThat(body.get()).isNull();
  }

  @Test
  void retryAfterAcceptsOnlySecondsAndIsCapped() {
    assertThat(WebPushSender.seconds(" 30 ")).contains(Duration.ofSeconds(30));
    assertThat(WebPushSender.seconds("999999999")).contains(WebPushSender.MAX_RETRY_AFTER);
    assertThat(WebPushSender.seconds("Wed, 21 Oct 2026 07:28:00 GMT")).isEmpty();
    assertThat(WebPushSender.seconds("-1")).isEmpty();
  }

  private WebPushSender sender(KeyPair vapidKeys) {
    return new WebPushSender(
        new Vapid(VapidTest.publicKey(vapidKeys), VapidTest.privateKey(vapidKeys), "mailto:a@b.c"),
        HttpClient.newHttpClient(),
        Duration.ofSeconds(5),
        Clock.fixed(Instant.parse("2026-10-26T00:00:00Z"), ZoneOffset.UTC));
  }

  private String endpoint() {
    return "http://127.0.0.1:" + server.getAddress().getPort() + "/push/abc";
  }

  private PushDevice validDevice() throws Exception {
    KeyPair device = VapidTest.keyPair();
    return new PushDevice(
        endpoint(),
        WebPushCryptoTest.b64(WebPushCrypto.encodePublic((ECPublicKey) device.getPublic())),
        WebPushCryptoTest.b64(new byte[16]));
  }

  private static PushMessage message(PushDevice device) {
    return new PushMessage(device, new byte[] {'{', '}'}, Duration.ofHours(1), "normal");
  }
}
