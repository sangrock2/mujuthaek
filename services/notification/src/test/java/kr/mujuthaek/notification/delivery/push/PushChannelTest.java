package kr.mujuthaek.notification.delivery.push;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.notification.delivery.DeliveryException;
import kr.mujuthaek.notification.delivery.OutgoingNotification;
import kr.mujuthaek.notification.notification.NotificationRequest.PushDevice;
import kr.mujuthaek.notification.notification.NotificationRequest.Recipient;
import kr.mujuthaek.notification.notification.NotificationType;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

/** 기기마다 보낸 결과를 어떻게 다루는지, 받을 곳 거르기, 내용 모양 (DB·네트워크 없이). */
class PushChannelTest {

  final JsonMapper json = JsonMapper.builder().build();
  final Scripted sender = new Scripted();
  final ExpiredSubscriptions expired = mock(ExpiredSubscriptions.class);
  final PushChannel channel =
      new PushChannel(
          sender,
          new PushProperties(
              "log",
              "",
              "",
              "mailto:a@b.c",
              List.of("fcm.googleapis.com", "push.apple.com"),
              Duration.ofSeconds(5)),
          json,
          expired);
  final UUID user = UUID.randomUUID();

  @Test
  void addressKeepsOnlyUsableDevicesUpToFive() {
    List<PushDevice> devices = new ArrayList<>();
    devices.add(device("https://evil.example.com/x"));
    devices.add(device("http://fcm.googleapis.com/x"));
    devices.add(new PushDevice("https://fcm.googleapis.com/no-keys", " ", "a"));
    devices.add(null);
    for (int i = 0; i < 6; i++) {
      devices.add(device("https://fcm.googleapis.com/" + i));
    }

    String address = channel.address(new Recipient(user, null, false, devices)).orElseThrow();

    assertThat(address)
        .contains("https://fcm.googleapis.com/0")
        .contains("https://fcm.googleapis.com/4")
        .doesNotContain("https://fcm.googleapis.com/5")
        .doesNotContain("evil")
        .doesNotContain("http://");
  }

  @Test
  void noDevicesMeansNoPushDelivery() {
    assertThat(channel.address(Recipient.emailOnly(user, "me@example.com", false))).isEmpty();
    assertThat(channel.address(new Recipient(user, null, false, List.of()))).isEmpty();
    assertThat(
            channel.address(
                new Recipient(user, null, false, List.of(device("https://evil.example.com/x")))))
        .isEmpty();
  }

  @Test
  void partlyDeliveredKeepsOnlyTheDevicesToRetry() throws Exception {
    sender.plan("https://fcm.googleapis.com/a", 201);
    sender.plan("https://fcm.googleapis.com/b", 500);
    sender.plan("https://web.push.apple.com/c", 410);
    sender.failWithIo("https://fcm.googleapis.com/d");

    DeliveryException e =
        catchDelivery(
            address(
                "https://fcm.googleapis.com/a",
                "https://fcm.googleapis.com/b",
                "https://web.push.apple.com/c",
                "https://fcm.googleapis.com/d"));

    assertThat(e.permanent()).isFalse();
    verify(expired).report(user, "https://web.push.apple.com/c", 410); // 죽은 기기는 api에 알려요
    verifyNoMoreInteractions(expired);
    assertThat(e.remainingAddress().orElseThrow())
        .contains("/b")
        .contains("/d")
        .doesNotContain("/a")
        .doesNotContain("/c");
  }

  @Test
  void deliveredToSomeAndExpiredForOthersIsSent() throws Exception {
    sender.plan("https://fcm.googleapis.com/a", 201);
    sender.plan("https://fcm.googleapis.com/b", 404);

    channel.send(
        user,
        address("https://fcm.googleapis.com/a", "https://fcm.googleapis.com/b"),
        one(NotificationType.CORRECTED));

    assertThat(sender.sent).hasSize(2);
    verify(expired).report(user, "https://fcm.googleapis.com/b", 404);
  }

  @Test
  void permanentOutcomes() {
    sender.plan("https://fcm.googleapis.com/gone", 410);
    assertThat(catchDelivery(address("https://fcm.googleapis.com/gone")).code())
        .isEqualTo("ALL_EXPIRED");

    sender.plan("https://fcm.googleapis.com/bad", 400);
    DeliveryException bad = catchDelivery(address("https://fcm.googleapis.com/bad"));
    assertThat(bad.permanent()).isTrue();
    assertThat(bad.code()).isEqualTo("PUSH_400");

    sender.plan("https://fcm.googleapis.com/key", 403);
    sender.plan("https://fcm.googleapis.com/never", 201);
    DeliveryException key =
        catchDelivery(
            address("https://fcm.googleapis.com/key", "https://fcm.googleapis.com/never"));
    assertThat(key.code()).isEqualTo("PUSH_403");
    assertThat(key.permanent()).isTrue();
    assertThat(sender.endpoints())
        .as("기기는 동시에 보내서 다른 기기에도 보내 봐요")
        .contains("https://fcm.googleapis.com/never");
  }

  @Test
  void devicesAreSentToAtTheSameTime() throws Exception {
    // 두 기기가 동시에 보내져야만 둘 다 이 지점을 지나요 (차례로 보내면 첫 기기가 기다리다 시간 초과)
    var together = new java.util.concurrent.CyclicBarrier(2);
    PushChannel concurrent =
        new PushChannel(
            message -> {
              try {
                together.await(5, java.util.concurrent.TimeUnit.SECONDS);
              } catch (Exception e) {
                throw new java.io.IOException("동시에 보내지 않았어요");
              }
              return new PushResponse(201, null);
            },
            new PushProperties(
                "log",
                "",
                "",
                "mailto:a@b.c",
                List.of("fcm.googleapis.com"),
                Duration.ofSeconds(5)),
            json,
            expired);

    assertThat(
            concurrent.send(
                user,
                address("https://fcm.googleapis.com/a", "https://fcm.googleapis.com/b"),
                one(NotificationType.CORRECTED)))
        .isNull();
  }

  @Test
  void tooManyRequestsCarriesTheLongestRetryAfter() {
    sender.plan("https://fcm.googleapis.com/a", 429);
    sender.retryAfter.put("https://fcm.googleapis.com/a", Duration.ofMinutes(3));
    sender.plan("https://fcm.googleapis.com/b", 429);
    sender.retryAfter.put("https://fcm.googleapis.com/b", Duration.ofMinutes(9));

    DeliveryException e =
        catchDelivery(address("https://fcm.googleapis.com/a", "https://fcm.googleapis.com/b"));

    assertThat(e.code()).isEqualTo("PUSH_429");
    assertThat(e.retryAfter()).contains(Duration.ofMinutes(9));
  }

  @Test
  void deviceThatSlippedPastTheAllowListIsNotCalled() {
    // api·address()가 거르지만, 저장된 줄을 직접 고친 경우에도 남의 서버를 부르지 않아요
    DeliveryException e =
        catchDelivery(
            "[{\"endpoint\":\"https://evil.example.com/x\",\"p256dh\":\"k\",\"auth\":\"a\"}]");

    assertThat(e.code()).isEqualTo("PUSH_ENDPOINT_NOT_ALLOWED");
    assertThat(sender.sent).isEmpty();
  }

  @Test
  void singlePayloadCutsLongTextAndTagsTheScreen() {
    String payload =
        text(
            channel.payload(
                List.of(
                    new OutgoingNotification(
                        NotificationType.DEADLINE_D1,
                        "가".repeat(150),
                        "줄\n바꿈 " + "나".repeat(300),
                        "/notices/1"))));

    assertThat(payload)
        .startsWith("{\"v\":1,\"type\":\"DEADLINE_D1\"")
        .contains("\"title\":\"" + "가".repeat(99) + "…\"")
        .contains("\"body\":\"줄 바꿈 ")
        .contains("\"tag\":\"/notices/1\"");
  }

  @Test
  void digestPayloadNamesTheFirstAndCountsTheRest() {
    String payload =
        text(
            channel.payload(
                List.of(
                    new OutgoingNotification(
                        NotificationType.NEW_NOTICE, "새 공고: 서리풀 청년아트타운", "b", "/notices/1"),
                    new OutgoingNotification(
                        NotificationType.NEW_SUPPORT, "새 정책: 청년 월세", "b", "/benefits/2"),
                    new OutgoingNotification(
                        NotificationType.NEW_NOTICE,
                        "새 공고: 행복주택",
                        "b",
                        "/notices/3",
                        java.util.UUID.fromString("01a17700-0000-7000-8000-000000000003")))));

    assertThat(payload)
        // 기기가 「떴어요·눌렀어요」를 알릴 알림함 줄 ID (없는 줄은 빼요)
        .contains("\"ids\":[\"01a17700-0000-7000-8000-000000000003\"]")
        .contains("\"type\":\"NEW_DIGEST\"")
        .contains("\"title\":\"새 소식 3건\"")
        .contains("\"body\":\"서리풀 청년아트타운 외 2건\"")
        .contains("\"linkPath\":\"/notifications\"");
  }

  @Test
  void aLargeDigestIsSentWithOnlyAsManyIdsAsFit() throws Exception {
    // 2026-11-10 코드 검토: 한 칸에 90건 남짓이 쌓이면 ID 목록만으로 한도를 넘어, 묶음 전체가 PUSH_PAYLOAD_TOO_LARGE로 실패했음
    List<OutgoingNotification> many = new java.util.ArrayList<>();
    for (int i = 0; i < 150; i++) {
      many.add(
          new OutgoingNotification(
              NotificationType.NEW_SUPPORT,
              "새 정책: 청년 월세 " + i,
              "b",
              "/benefits/" + i,
              java.util.UUID.randomUUID()));
    }
    byte[] payload = channel.payload(many);
    assertThat(payload.length).isLessThanOrEqualTo(WebPushCrypto.MAX_PLAINTEXT_BYTES);
    assertThat(text(payload))
        .contains("\"title\":\"새 소식 150건\"")
        .contains(many.get(0).inboxId().toString());

    channel.send(user, address("https://fcm.googleapis.com/a"), many); // 실패하지 않고 보냄
    assertThat(sender.sent).hasSize(1);
  }

  @Test
  void ttlAndUrgencyFollowTheType() throws Exception {
    assertThat(PushChannel.ttl(NotificationType.DEADLINE_D1, false)).hasHours(12);
    assertThat(PushChannel.ttl(NotificationType.DEADLINE_D3, false)).hasHours(48);
    assertThat(PushChannel.ttl(NotificationType.NEW_SUPPORT, false)).hasHours(24);
    assertThat(PushChannel.ttl(NotificationType.FOLLOW_UP, false)).hasHours(72);
    assertThat(PushChannel.ttl(NotificationType.CORRECTED, true)).hasHours(24);

    channel.send(user, address("https://fcm.googleapis.com/a"), one(NotificationType.DEADLINE_D3));
    assertThat(sender.sent.getFirst().urgency()).isEqualTo("normal");
  }

  @Test
  void brokenAddressOrHugePayloadFailsForGood() {
    assertThat(catchDelivery("not json").code()).isEqualTo("PUSH_ADDRESS_UNREADABLE");

    DeliveryException huge =
        catchDelivery(
            address("https://fcm.googleapis.com/a"),
            List.of(
                new OutgoingNotification(
                    NotificationType.CORRECTED, "t", "b", "/" + "x".repeat(5000))));
    assertThat(huge.code()).isEqualTo("PUSH_PAYLOAD_TOO_LARGE");
    assertThat(huge.permanent()).isTrue();
  }

  private DeliveryException catchDelivery(String address) {
    return catchDelivery(address, one(NotificationType.CORRECTED));
  }

  private DeliveryException catchDelivery(
      String address, List<OutgoingNotification> notifications) {
    try {
      channel.send(user, address, notifications);
    } catch (DeliveryException e) {
      return e;
    }
    throw new AssertionError("DeliveryException이 나야 해요");
  }

  private String address(String... endpoints) {
    return json.writeValueAsString(
        java.util.Arrays.stream(endpoints).map(PushChannelTest::device).toList());
  }

  private static PushDevice device(String endpoint) {
    return new PushDevice(endpoint, "p256dh", "auth");
  }

  private static List<OutgoingNotification> one(NotificationType type) {
    return List.of(new OutgoingNotification(type, "제목", "본문", "/notices/1"));
  }

  private static String text(byte[] bytes) {
    return new String(bytes, StandardCharsets.UTF_8);
  }

  static class Scripted implements PushSender {
    final List<PushMessage> sent = new java.util.concurrent.CopyOnWriteArrayList<>();
    final Map<String, Integer> statuses = new HashMap<>();
    final Map<String, Duration> retryAfter = new HashMap<>();
    final List<String> io = new ArrayList<>();

    void plan(String endpoint, int status) {
      statuses.put(endpoint, status);
    }

    void failWithIo(String endpoint) {
      io.add(endpoint);
    }

    List<String> endpoints() {
      return sent.stream().map(m -> m.device().endpoint()).toList();
    }

    @Override
    public PushResponse send(PushMessage message) throws IOException {
      sent.add(message);
      String endpoint = message.device().endpoint();
      if (io.contains(endpoint)) {
        throw new IOException("timeout");
      }
      return new PushResponse(statuses.getOrDefault(endpoint, 201), retryAfter.get(endpoint));
    }
  }
}
