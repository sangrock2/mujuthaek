package kr.mujuthaek.notification.delivery;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import kr.mujuthaek.notification.TestcontainersConfiguration;
import kr.mujuthaek.notification.delivery.email.EmailMessage;
import kr.mujuthaek.notification.delivery.email.EmailSender;
import kr.mujuthaek.notification.delivery.push.PushMessage;
import kr.mujuthaek.notification.delivery.push.PushResponse;
import kr.mujuthaek.notification.delivery.push.PushSender;
import kr.mujuthaek.notification.notification.NotificationRequest;
import kr.mujuthaek.notification.notification.NotificationRequest.PushDevice;
import kr.mujuthaek.notification.notification.NotificationRequest.Recipient;
import kr.mujuthaek.notification.notification.NotificationService;
import kr.mujuthaek.notification.notification.NotificationType;
import kr.mujuthaek.notification.notification.TargetType;
import kr.mujuthaek.notification.notification.UserDataCleaner;
import kr.mujuthaek.notification.support.TimeConfig;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 알림 요청 → 발송 줄 → 워커 → 채널까지. 이메일·웹 푸시 모두 실제로 보내지 않고 기록만 하는 가짜 발송기를 끼워요 (채널은 진짜
 * EmailChannel·PushChannel).
 */
@SpringBootTest(properties = "notification.delivery.poll-enabled=false")
@Import({TestcontainersConfiguration.class, DeliveryFlowTest.Fakes.class})
public class DeliveryFlowTest {

  static final UUID USER = UUID.fromString("0192b6f0-0000-7000-8000-0000000000a1");
  static final Recipient EMAIL_ONLY = Recipient.emailOnly(USER, "me@example.com", false);

  @Autowired NotificationService service;
  @Autowired DeliveryWorker worker;
  @Autowired UserDataCleaner cleaner;
  @Autowired TransactionTemplate tx;
  @Autowired JdbcClient jdbc;
  @Autowired MutableClock clock;
  @Autowired RecordingEmailSender email;
  @Autowired RecordingPushSender push;
  @Autowired DeliveryRepository deliveries;
  @Autowired DeliverySchedule schedule;
  @Autowired List<NotificationChannel> channels;

  @BeforeEach
  void setUp() {
    jdbc.sql("delete from deliveries").update();
    jdbc.sql("delete from withdrawn_users").update();
    jdbc.sql("delete from outbox").update();
    email.sent.clear();
    email.failure.set(null);
    push.sent.clear();
    push.statuses.clear();
    push.onSend = null;
    push.retryAfter = null;
    clock.set("2026-10-23T10:00");
  }

  @Test
  void immediateNotificationIsSentOnceAndAddressIsCleared() {
    request(NotificationType.CORRECTED, "NOTICE:X:CORRECTED:2", EMAIL_ONLY);
    request(NotificationType.CORRECTED, "NOTICE:X:CORRECTED:2", EMAIL_ONLY); // 같은 알림 다시

    worker.runOnce();

    assertThat(email.sent).hasSize(1);
    assertThat(email.sent.getFirst().to()).isEqualTo("me@example.com");
    assertThat(email.sent.getFirst().subject()).isEqualTo("[무주택자들] 제목 NOTICE:X:CORRECTED:2");
    assertThat(status(Channel.EMAIL)).containsExactly("SENT");
    assertThat(jdbc.sql("select address from deliveries").query(String.class).optional())
        .isEmpty(); // 보낸 뒤에는 주소를 남기지 않아요
  }

  @Test
  void recipientWithoutAddressGetsNoDelivery() {
    request(
        NotificationType.CORRECTED, "NOTICE:X:CORRECTED:2", Recipient.emailOnly(USER, null, false));

    assertThat(jdbc.sql("select count(*) from deliveries").query(Long.class).single()).isZero();
  }

  @Test
  void newNoticesAreBundledIntoOneEmailAtSixPm() {
    request(NotificationType.NEW_NOTICE, "NOTICE:A:NEW", EMAIL_ONLY);
    request(NotificationType.NEW_NOTICE, "NOTICE:B:NEW", EMAIL_ONLY);

    worker.runOnce();
    assertThat(email.sent).isEmpty(); // 10시: 아직 묶음 시각 전

    clock.set("2026-10-23T18:00");
    worker.runOnce();
    assertThat(email.sent).hasSize(1);
    assertThat(email.sent.getFirst().subject()).isEqualTo("[무주택자들] 관심 조건에 맞는 새 소식 2건");
    assertThat(status(Channel.EMAIL)).containsExactly("SENT", "SENT");
  }

  @Test
  void quietHoursPostponeUntilEight() {
    clock.set("2026-10-23T23:00");
    request(
        NotificationType.DEADLINE_D1,
        "NOTICE:X:D1:2026-10-24",
        Recipient.emailOnly(USER, "me@example.com", true));

    worker.runOnce();
    assertThat(email.sent).isEmpty();

    clock.set("2026-10-24T08:00");
    worker.runOnce();
    assertThat(email.sent).hasSize(1);
  }

  @Test
  void temporaryFailureIsRetriedAndPermanentFailureStops() {
    email.failure.set(new DeliveryException("SES_TooManyRequests", false));
    request(NotificationType.DEADLINE_D3, "NOTICE:X:D3:2026-10-26", EMAIL_ONLY);

    worker.runOnce();
    assertThat(status(Channel.EMAIL)).containsExactly("PENDING");

    clock.set("2026-10-23T10:01");
    email.failure.set(new DeliveryException("SES_MessageRejected", true));
    worker.runOnce();
    assertThat(status(Channel.EMAIL)).containsExactly("FAILED");
    assertThat(jdbc.sql("select attempts from deliveries").query(Integer.class).single())
        .isEqualTo(2);
  }

  @Test
  void withdrawnUserLosesPendingDeliveries() {
    request(NotificationType.NEW_NOTICE, "NOTICE:A:NEW", EMAIL_ONLY);

    tx.executeWithoutResult(s -> cleaner.delete(USER));

    clock.set("2026-10-23T18:00");
    worker.runOnce();
    assertThat(email.sent).isEmpty();
  }

  @Test
  void requestThatArrivesAfterWithdrawalSkipsThatMember() {
    UUID other = UUID.fromString("0192b6f0-0000-7000-8000-0000000000b2");
    tx.executeWithoutResult(s -> cleaner.delete(USER)); // user.withdrawn이 먼저 옴

    // 탈퇴 전에 api가 만든 요청이 재시도로 늦게 옴
    UUID targetId = UUID.randomUUID();
    tx.executeWithoutResult(
        s ->
            service.handle(
                new NotificationRequest(
                    NotificationType.CORRECTED,
                    "NOTICE:X:CORRECTED:2",
                    new NotificationRequest.Target(TargetType.NOTICE, targetId),
                    "제목",
                    "본문",
                    "/notices/" + targetId,
                    List.of(EMAIL_ONLY, Recipient.emailOnly(other, "other@example.com", false)))));

    assertThat(jdbc.sql("select user_id from deliveries").query(UUID.class).list())
        .containsExactly(other);
  }

  @Test
  void pushDeadlineGoesToEveryDeviceRightAwayInOneDelivery() {
    request(NotificationType.DEADLINE_D1, "NOTICE:X:D1:2026-10-24", pushTo("a", "b"));

    worker.runOnce();

    assertThat(push.endpoints())
        .containsExactlyInAnyOrder(device("a").endpoint(), device("b").endpoint());
    assertThat(push.sent.getFirst().urgency()).isEqualTo("high");
    assertThat(push.sent.getFirst().ttl()).hasHours(12);
    assertThat(status(Channel.PUSH)).containsExactly("SENT"); // 회원 1명·채널 1개 = 발송 줄 1개
    assertThat(jdbc.sql("select address from deliveries").query(String.class).optional())
        .isEmpty(); // 보낸 뒤에는 기기 목록을 남기지 않아요
  }

  @Test
  void newNoticesOnPushAreBundledEveryThirtyMinutesWithTheLatestDevices() {
    clock.set("2026-10-23T10:07");
    request(NotificationType.NEW_NOTICE, "NOTICE:A:NEW", pushTo("a"));
    clock.set("2026-10-23T10:12");
    request(NotificationType.NEW_NOTICE, "NOTICE:B:NEW", pushTo("a", "b")); // 그사이 기기 b 등록

    worker.runOnce();
    assertThat(push.sent).isEmpty(); // 10:30 칸 전

    clock.set("2026-10-23T10:30");
    worker.runOnce();
    assertThat(push.endpoints())
        .containsExactlyInAnyOrder(device("a").endpoint(), device("b").endpoint());
    assertThat(push.payload(0))
        .contains("\"type\":\"NEW_DIGEST\"")
        .contains("\"title\":\"새 소식 2건\"")
        .contains("\"body\":\"제목 NOTICE:A:NEW 외 1건\"")
        .contains("\"linkPath\":\"/notifications\"");
    assertThat(status(Channel.PUSH)).containsExactly("SENT", "SENT");
  }

  @Test
  void pushBundleThatFallsIntoQuietHoursWaitsUntilEight() {
    clock.set("2026-10-23T21:50");
    request(
        NotificationType.NEW_NOTICE,
        "NOTICE:A:NEW",
        new Recipient(USER, null, true, List.of(device("a"))));

    clock.set("2026-10-23T22:00");
    worker.runOnce();
    assertThat(push.sent).isEmpty();

    clock.set("2026-10-24T08:00");
    worker.runOnce();
    assertThat(push.sent).hasSize(1);
    assertThat(push.payload(0)).contains("\"title\":\"제목 NOTICE:A:NEW\""); // 1건은 묶음 문구 없이
  }

  @Test
  void onlyDevicesThatMissedItAreRetried() {
    push.statuses.put(device("a").endpoint(), new ArrayDeque<>(List.of(503, 201)));
    request(NotificationType.CORRECTED, "NOTICE:X:CORRECTED:2", pushTo("a", "b"));

    worker.runOnce();
    assertThat(push.endpoints())
        .containsExactlyInAnyOrder(device("a").endpoint(), device("b").endpoint());
    assertThat(status(Channel.PUSH)).containsExactly("PENDING");
    assertThat(jdbc.sql("select address from deliveries").query(String.class).single())
        .contains(device("a").endpoint())
        .doesNotContain(device("b").endpoint());

    clock.set("2026-10-23T10:01");
    worker.runOnce();
    assertThat(push.endpoints())
        .containsExactlyInAnyOrder(
            device("a").endpoint(), device("b").endpoint(), device("a").endpoint()); // b는 한 번만
    assertThat(status(Channel.PUSH)).containsExactly("SENT");
  }

  @Test
  void aRowSomeDeviceReceivedIsSentEvenWhenTheOthersRunOutOfRetries() {
    // 2026-11-10 코드 검토: b가 받았는데 a가 재시도를 다 쓰면 줄이 FAILED로 남아 발송 통계 실패가 부풀었음(계약: 한 대라도 받았으면 SENT)
    push.statuses.put(device("a").endpoint(), new ArrayDeque<>(List.of(503, 503, 503, 503)));
    request(NotificationType.CORRECTED, "NOTICE:X:CORRECTED:3", pushTo("a", "b"));

    for (String at :
        List.of("2026-10-23T10:00", "2026-10-23T10:02", "2026-10-23T10:08", "2026-10-23T10:40")) {
      clock.set(at);
      worker.runOnce();
    }
    assertThat(status(Channel.PUSH)).containsExactly("SENT");
  }

  @Test
  void aRowSomeDeviceReceivedStaysSentWhenALaterRetryHitsAnUnexpectedError() {
    // 2026-11-10 재검토: 남은 기기를 다시 보내다 예상 못한 오류가 나면 「이미 받음」 표시를 잃어, 재시도를 다 쓰면 FAILED였음
    push.statuses.put(device("a").endpoint(), new ArrayDeque<>(List.of(503)));
    request(NotificationType.CORRECTED, "NOTICE:X:CORRECTED:4", pushTo("a", "b"));
    worker.runOnce(); // b는 받고 a는 다시

    push.onSend =
        () -> {
          throw new IllegalStateException("예상 못한 오류");
        };
    for (String at : List.of("2026-10-23T10:02", "2026-10-23T10:08", "2026-10-23T10:40")) {
      clock.set(at);
      worker.runOnce();
    }
    assertThat(status(Channel.PUSH)).containsExactly("SENT");
  }

  @Test
  void deliveryFailsWhenEveryDeviceIsGone() {
    push.statuses.put(device("a").endpoint(), new ArrayDeque<>(List.of(410)));
    push.statuses.put(device("b").endpoint(), new ArrayDeque<>(List.of(404)));
    request(NotificationType.CORRECTED, "NOTICE:X:CORRECTED:2", pushTo("a", "b"));

    worker.runOnce();

    assertThat(status(Channel.PUSH)).containsExactly("FAILED");
    assertThat(jdbc.sql("select last_error from deliveries").query(String.class).single())
        .isEqualTo("ALL_EXPIRED");
    // 죽은 기기는 발송 결과와 같은 트랜잭션에서 아웃박스에 (api가 받아 그 기기를 지워요)
    assertThat(
            jdbc.sql(
                    "select payload->'payload'->>'endpoint' from outbox"
                        + " where event_type = 'push.subscription.expired' order by 1")
                .query(String.class)
                .list())
        .containsExactly(device("a").endpoint(), device("b").endpoint());
    assertThat(
            jdbc.sql("select distinct payload->>'producer' from outbox")
                .query(String.class)
                .single())
        .isEqualTo("notification");
  }

  @Test
  void tooManyRequestsWaitsAsLongAsThePushServiceAsks() {
    push.statuses.put(device("a").endpoint(), new ArrayDeque<>(List.of(429, 201)));
    push.retryAfter = Duration.ofMinutes(10);
    request(NotificationType.CORRECTED, "NOTICE:X:CORRECTED:2", pushTo("a"));

    worker.runOnce();
    clock.set("2026-10-23T10:05"); // 정한 재시도(1분)는 지났지만 10분을 기다려요
    worker.runOnce();
    assertThat(push.sent).hasSize(1);

    clock.set("2026-10-23T10:10");
    worker.runOnce();
    assertThat(push.sent).hasSize(2);
    assertThat(status(Channel.PUSH)).containsExactly("SENT");
  }

  @Test
  void sendingHoldsNoDatabaseLockButMarksTheRowAsTaken() {
    request(NotificationType.CORRECTED, "NOTICE:X:CORRECTED:2", pushTo("a"));
    List<String> seen = new java.util.ArrayList<>();
    push.onSend =
        () -> {
          // 보내는 동안 다른 연결이 그 줄을 바로 잠글 수 있어야 해요 (nowait: 잠겨 있으면 바로 오류)
          seen.add(
              jdbc.sql("select status from deliveries for update nowait")
                  .query(String.class)
                  .single());
          seen.add(
              jdbc.sql("select (locked_until is not null)::text from deliveries")
                  .query(String.class)
                  .single());
        };

    worker.runOnce();

    assertThat(seen).containsExactly("PENDING", "true");
    assertThat(
            jdbc.sql("select (locked_until is null)::text || status from deliveries")
                .query(String.class)
                .single())
        .as("결과를 적으며 맡기를 풀어요")
        .isEqualTo("trueSENT");
  }

  @Test
  void rowTakenByAnotherServerIsSkippedUntilItsLeaseRunsOut() {
    request(NotificationType.CORRECTED, "NOTICE:X:CORRECTED:2", pushTo("a"));
    // 다른 서버가 맡고 보내다가 죽음 (결과를 못 적음)
    jdbc.sql("update deliveries set locked_until = :until")
        .param(
            "until", clock.instant().plus(DeliveryWorker.LEASE).atOffset(java.time.ZoneOffset.UTC))
        .update();

    assertThat(worker.runOnce()).isZero();
    assertThat(push.sent).isEmpty();

    clock.set("2026-10-23T10:11"); // 맡은 시간(10분)이 지남
    assertThat(worker.runOnce()).isEqualTo(1);
    assertThat(push.sent).hasSize(1);
    assertThat(status(Channel.PUSH)).containsExactly("SENT");
  }

  @Test
  void recipientsAreSentAtTheSameTimeNotOneByOne() {
    // 푸시 서비스가 느려도(200ms) 한 명씩 기다리지 않고 회원끼리 동시에 보내요
    AtomicInteger most = trackInFlight(Duration.ofMillis(200));
    for (int i = 0; i < 10; i++) {
      request(NotificationType.CORRECTED, "NOTICE:X:CORRECTED:" + i, pushTo("u" + i));
    }

    assertThat(worker.runOnce()).isEqualTo(10);

    assertThat(most.get()).isGreaterThan(1);
    assertThat(push.sent).hasSize(10);
    assertThat(status(Channel.PUSH)).hasSize(10).containsOnly("SENT");
  }

  @Test
  void sendsNoMoreThanConcurrencyAtOnce() {
    DeliveryWorker limited = new DeliveryWorker(deliveries, schedule, channels, tx, 100, 2);
    AtomicInteger most = trackInFlight(Duration.ofMillis(100));
    for (int i = 0; i < 6; i++) {
      request(NotificationType.CORRECTED, "NOTICE:X:CORRECTED:" + i, pushTo("u" + i));
    }

    assertThat(limited.runOnce()).isEqualTo(6);

    assertThat(most.get()).isEqualTo(2);
    assertThat(status(Channel.PUSH)).hasSize(6).containsOnly("SENT");
  }

  @Test
  void oneRecipientFailingDoesNotStopTheOthers() {
    push.statuses.put(device("bad").endpoint(), new ArrayDeque<>(List.of(400)));
    request(NotificationType.CORRECTED, "NOTICE:X:CORRECTED:1", pushTo("bad"));
    request(NotificationType.CORRECTED, "NOTICE:X:CORRECTED:2", pushTo("ok1"));
    request(NotificationType.CORRECTED, "NOTICE:X:CORRECTED:3", pushTo("ok2"));

    worker.runOnce();

    assertThat(status(Channel.PUSH)).containsExactly("FAILED", "SENT", "SENT");
  }

  /** 보내는 데 took만큼 걸리게 하고, 동시에 보내는 중이던 가장 많은 수를 세요 */
  private AtomicInteger trackInFlight(Duration took) {
    AtomicInteger now = new AtomicInteger();
    AtomicInteger most = new AtomicInteger();
    push.onSend =
        () -> {
          most.accumulateAndGet(now.incrementAndGet(), Math::max);
          try {
            Thread.sleep(took);
          } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
          } finally {
            now.decrementAndGet();
          }
        };
    return most;
  }

  private static Recipient pushTo(String... names) {
    return new Recipient(
        USER, null, false, java.util.Arrays.stream(names).map(DeliveryFlowTest::device).toList());
  }

  static PushDevice device(String name) {
    return new PushDevice(
        "https://fcm.googleapis.com/fcm/send/" + name, "p256dh-" + name, "auth-" + name);
  }

  private void request(NotificationType type, String dedupKey, Recipient recipient) {
    UUID targetId = UUID.randomUUID();
    NotificationRequest request =
        new NotificationRequest(
            type,
            dedupKey,
            new NotificationRequest.Target(TargetType.NOTICE, targetId),
            "제목 " + dedupKey,
            "본문",
            "/notices/" + targetId,
            List.of(recipient));
    tx.executeWithoutResult(s -> service.handle(request));
  }

  private List<String> status(Channel channel) {
    return jdbc.sql("select status from deliveries where channel = :c order by status")
        .param("c", channel.name())
        .query(String.class)
        .list();
  }

  /** 다른 테스트도 같은 설정을 써서 테스트 컨텍스트(컨테이너)를 하나만 띄워요 */
  @TestConfiguration(proxyBeanMethods = false)
  public static class Fakes {

    @Bean
    @Primary
    MutableClock mutableClock() {
      return new MutableClock();
    }

    @Bean
    @Primary
    RecordingEmailSender recordingEmailSender() {
      return new RecordingEmailSender();
    }

    @Bean
    @Primary
    RecordingPushSender recordingPushSender() {
      return new RecordingPushSender();
    }
  }

  public static class MutableClock extends Clock {
    private final AtomicReference<Instant> now = new AtomicReference<>(Instant.now());

    public void set(String seoulLocalDateTime) {
      now.set(ZonedDateTime.parse(seoulLocalDateTime + ":00+09:00[Asia/Seoul]").toInstant());
    }

    @Override
    public ZoneId getZone() {
      return TimeConfig.SEOUL;
    }

    @Override
    public Clock withZone(ZoneId zone) {
      return Clock.fixed(now.get(), zone);
    }

    @Override
    public Instant instant() {
      return now.get();
    }
  }

  public static class RecordingEmailSender implements EmailSender {
    public final List<EmailMessage> sent = new CopyOnWriteArrayList<>();
    final AtomicReference<DeliveryException> failure = new AtomicReference<>();

    @Override
    public String send(EmailMessage message) throws DeliveryException {
      if (failure.get() != null) {
        throw failure.get();
      }
      sent.add(message);
      return "fake-" + sent.size();
    }
  }

  /** 보내지 않고 기록만 해요. 기기마다 돌려줄 상태 코드를 미리 정할 수 있어요 (없으면 201) */
  public static class RecordingPushSender implements PushSender {
    public final List<PushMessage> sent = new CopyOnWriteArrayList<>();
    final Map<String, Deque<Integer>> statuses = new ConcurrentHashMap<>();
    volatile Duration retryAfter;

    /** 보내는 순간에 할 일 (테스트가 그때 DB 상태를 봐요) */
    volatile Runnable onSend;

    @Override
    public PushResponse send(PushMessage message) {
      if (onSend != null) {
        onSend.run();
      }
      sent.add(message);
      Deque<Integer> planned = statuses.get(message.device().endpoint());
      int status = planned == null || planned.isEmpty() ? 201 : planned.poll();
      return new PushResponse(status, status == 429 ? retryAfter : null);
    }

    List<String> endpoints() {
      return sent.stream().map(m -> m.device().endpoint()).toList();
    }

    String payload(int index) {
      return new String(sent.get(index).payload(), StandardCharsets.UTF_8);
    }
  }
}
