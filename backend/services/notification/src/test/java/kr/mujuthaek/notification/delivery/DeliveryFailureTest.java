package kr.mujuthaek.notification.delivery;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import kr.mujuthaek.notification.TestcontainersConfiguration;
import kr.mujuthaek.notification.delivery.DeliveryFlowTest.MutableClock;
import kr.mujuthaek.notification.delivery.DeliveryFlowTest.RecordingEmailSender;
import kr.mujuthaek.notification.notification.NotificationRequest;
import kr.mujuthaek.notification.notification.NotificationRequest.Recipient;
import kr.mujuthaek.notification.notification.NotificationService;
import kr.mujuthaek.notification.notification.NotificationType;
import kr.mujuthaek.notification.notification.TargetType;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

/** 발송이 경계 상황(묶음이 한 번에 꺼내는 양보다 큼, 워커 두 대, 이상한 제목)에서도 한 번씩 제대로 나가는지. */
@SpringBootTest(properties = "notification.delivery.poll-enabled=false")
@Import({TestcontainersConfiguration.class, DeliveryFlowTest.Fakes.class})
class DeliveryFailureTest {

  static final UUID USER = UUID.fromString("0192b6f0-0000-7000-8000-0000000000b1");

  @Autowired NotificationService service;
  @Autowired DeliveryWorker worker;
  @Autowired TransactionTemplate tx;
  @Autowired JdbcClient jdbc;
  @Autowired MutableClock clock;
  @Autowired RecordingEmailSender email;

  @BeforeEach
  void setUp() {
    jdbc.sql("delete from deliveries").update();
    jdbc.sql("delete from withdrawn_users").update();
    email.sent.clear();
    email.failure.set(null);
    clock.set("2026-10-23T10:00");
  }

  @Test
  void bigDigestIsStillOneEmail() {
    // 같은 회원의 새 공고 25건 (워커가 한 번에 꺼내는 양 20건보다 많음)
    for (int i = 0; i < 25; i++) {
      request(NotificationType.NEW_NOTICE, "NOTICE:" + i + ":NEW", "새 공고 " + i, USER);
    }
    clock.set("2026-10-23T18:00");

    while (worker.runOnce() > 0) {}

    assertThat(email.sent).as("묶음 메일은 1통이어야 해요").hasSize(1);
    assertThat(email.sent.getFirst().subject()).endsWith("새 소식 25건");
  }

  @Test
  void bigDigestIsOneEmailEvenWithTwoWorkers() throws Exception {
    for (int i = 0; i < 25; i++) {
      request(NotificationType.NEW_NOTICE, "NOTICE:" + i + ":NEW", "새 공고 " + i, USER);
    }
    clock.set("2026-10-23T18:00");

    runTwoWorkersAtOnce();

    assertThat(email.sent).as("워커 두 대가 동시에 돌아도 묶음 메일은 1통").hasSize(1);
    assertThat(email.sent.getFirst().subject()).endsWith("새 소식 25건");
  }

  @Test
  void digestRowsHeldByAnotherWorkerAreNotSentSeparately() throws Exception {
    for (int i = 0; i < 25; i++) {
      request(NotificationType.NEW_NOTICE, "NOTICE:" + i + ":NEW", "새 공고 " + i, USER);
    }
    clock.set("2026-10-23T18:00");

    // 다른 워커가 같은 묶음의 마지막 5줄을 잡고 있는 순간을 만들어요
    var locked = new CountDownLatch(1);
    var release = new CountDownLatch(1);
    var other =
        Executors.newSingleThreadExecutor()
            .submit(
                () ->
                    tx.executeWithoutResult(
                        s -> {
                          jdbc.sql(
                                  """
                                  select id from deliveries where status = 'PENDING'
                                   order by created_at desc limit 5 for update
                                  """)
                              .query(UUID.class)
                              .list();
                          locked.countDown();
                          try {
                            release.await();
                          } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                          }
                        }));
    locked.await();
    var mine = Executors.newSingleThreadExecutor().submit(() -> worker.runOnce());
    Thread.sleep(1_000); // 그동안 내 워커가 기다리든 보내든 하게
    release.countDown();
    other.get();
    mine.get();
    while (worker.runOnce() > 0) {}

    assertThat(email.sent).as("잡혀 있던 줄 때문에 묶음이 쪼개지면 안 돼요").hasSize(1);
    assertThat(email.sent.getFirst().subject()).endsWith("새 소식 25건");
  }

  @Test
  void twoWorkersAtOnceSendEachMailOnce() throws Exception {
    int users = 30;
    for (int i = 0; i < users; i++) {
      request(
          NotificationType.CORRECTED,
          "NOTICE:X:CORRECTED:2",
          "정정",
          UUID.nameUUIDFromBytes(("u" + i).getBytes()));
    }

    runTwoWorkersAtOnce();

    assertThat(email.sent).as("한 사람에게 두 번 가면 안 돼요").hasSize(users);
  }

  @Test
  void lineBreakInTitleDoesNotBreakSubject() {
    request(NotificationType.CORRECTED, "NOTICE:Y:CORRECTED:2", "정정: 제목\r\n줄바꿈", USER);

    worker.runOnce();

    assertThat(email.sent).hasSize(1);
    assertThat(email.sent.getFirst().subject()).doesNotContain("\n").doesNotContain("\r");
  }

  private void runTwoWorkersAtOnce() throws Exception {
    var pool = Executors.newFixedThreadPool(2);
    var start = new CountDownLatch(1);
    Callable<Integer> run =
        () -> {
          start.await();
          int n = 0;
          int got;
          while ((got = worker.runOnce()) > 0) {
            n += got;
          }
          return n;
        };
    var a = pool.submit(run);
    var b = pool.submit(run);
    start.countDown();
    a.get();
    b.get();
    pool.shutdown();
  }

  private void request(NotificationType type, String dedupKey, String title, UUID user) {
    UUID targetId = UUID.randomUUID();
    tx.executeWithoutResult(
        s ->
            service.handle(
                new NotificationRequest(
                    type,
                    dedupKey,
                    new NotificationRequest.Target(TargetType.NOTICE, targetId),
                    title,
                    "본문",
                    "/notices/" + targetId,
                    new ArrayList<>(List.of(Recipient.emailOnly(user, "me@example.com", false))))));
  }
}
