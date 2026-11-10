package kr.mujuthaek.notification.event;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import java.util.function.Supplier;
import kr.mujuthaek.notification.TestcontainersConfiguration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.simple.JdbcClient;

@SpringBootTest
@Import(TestcontainersConfiguration.class)
class IncomingEventListenerTest {

  private static final Duration WAIT = Duration.ofSeconds(10);

  @Autowired RabbitTemplate rabbit;
  @Autowired JdbcClient jdbc;

  @BeforeEach
  void clear() {
    jdbc.sql("delete from processed_events").update();
    jdbc.sql("delete from deliveries").update();
    jdbc.sql("delete from withdrawn_users").update();
    while (rabbit.receive(EventQueueConfig.DLQ) != null) {} // 다른 테스트가 남긴 실패 메시지
  }

  @Test
  void recordsEventOnce() throws Exception {
    UUID eventId = UUID.randomUUID();
    String body = event(eventId, "notification.requested");

    publish("notification.requested", body);
    publish("notification.requested", body); // 같은 이벤트가 두 번 와도

    await(() -> processed(eventId) == 1);
    Thread.sleep(500); // 두 번째 메시지도 처리될 시간
    assertThat(processed(eventId)).isEqualTo(1);
  }

  @Test
  void policyTargetsAreAccepted() throws Exception {
    // 창업지원 사업·사업공간 모집 알림 (api notice.policy_judgments, ID = rawPolicyId)
    for (String type : new String[] {"STARTUP_SUPPORT", "SPACE_RECRUITMENT"}) {
      UUID eventId = UUID.randomUUID();
      publish(
          "notification.requested",
          event(eventId, "notification.requested")
              .replace("\"type\":\"NOTICE\"", "\"type\":\"" + type + "\""));

      await(() -> processed(eventId) == 1);
    }
    assertThat(rabbit.receive(EventQueueConfig.DLQ, 500)).isNull();
  }

  @Test
  void reportAnsweredIsAcceptedAndNotDigested() throws Exception {
    // 제보 답변: 제보한 회원 한 명에게 묶지 않고 바로 (발송 줄의 type 제약도 확인)
    UUID eventId = UUID.randomUUID();
    publish(
        "notification.requested",
        event(eventId, "notification.requested")
            .replace("\"type\":\"DEADLINE_D1\"", "\"type\":\"REPORT_ANSWERED\"")
            .replace("\"email\":null", "\"email\":\"reporter@example.com\""));

    await(() -> processed(eventId) == 1);
    assertThat(rabbit.receive(EventQueueConfig.DLQ, 500)).isNull();
    assertThat(
            jdbc.sql("select count(*) from deliveries where type = 'REPORT_ANSWERED'")
                .query(Long.class)
                .single())
        .isEqualTo(1L);
    assertThat(kr.mujuthaek.notification.notification.NotificationType.REPORT_ANSWERED.digest())
        .isFalse();
  }

  @Test
  void payloadOutsideContractGoesToDeadLetterQueue() throws Exception {
    UUID eventId = UUID.randomUUID();
    publish(
        "notification.requested",
        """
        {"eventId":"%s","eventType":"notification.requested","schemaVersion":1,"payload":{"type":"NEW_NOTICE"}}
        """
            .formatted(eventId)); // recipients·target 없음

    assertThat(receiveDead()).isNotNull();
    assertThat(processed(eventId)).isZero();
  }

  @Test
  void brokenEnvelopeGoesToDeadLetterQueue() throws Exception {
    publish("notification.requested", "{\"eventType\":\"notification.requested\"}"); // eventId 없음

    assertDeadAndNotRecorded();
  }

  @Test
  void unknownSchemaVersionGoesToDeadLetterQueue() throws Exception {
    // 모양이 다를 수 있는 다음 버전을 처리했다고 기록하면 조용히 사라져요
    publish(
        "notification.requested",
        event(UUID.randomUUID(), "notification.requested")
            .replace("\"schemaVersion\":1", "\"schemaVersion\":2"));

    assertDeadAndNotRecorded();
  }

  @Test
  void eventTypeThisServerDoesNotHandleGoesToDeadLetterQueue() throws Exception {
    // 라우팅 키는 받는 종류인데 봉투의 eventType이 다른 경우
    publish("notification.requested", event(UUID.randomUUID(), "notice.published"));

    assertDeadAndNotRecorded();
  }

  private void assertDeadAndNotRecorded() {
    assertThat(receiveDead()).isNotNull();
    assertThat(jdbc.sql("select count(*) from processed_events").query(Long.class).single())
        .isZero();
  }

  private Message receiveDead() {
    Message dead = null;
    Instant until = Instant.now().plus(WAIT);
    while (dead == null && Instant.now().isBefore(until)) {
      dead = rabbit.receive(EventQueueConfig.DLQ, 500);
    }
    return dead;
  }

  private void publish(String routingKey, String body) {
    MessageProperties props = new MessageProperties();
    props.setContentType(MessageProperties.CONTENT_TYPE_JSON);
    rabbit.send(EventQueueConfig.EXCHANGE, routingKey, new Message(body.getBytes(), props));
  }

  private long processed(UUID eventId) {
    return jdbc.sql("select count(*) from processed_events where event_id = :id")
        .param("id", eventId)
        .query(Long.class)
        .single();
  }

  private static String event(UUID eventId, String eventType) {
    return """
        {"eventId":"%s","eventType":"%s","schemaVersion":1,"occurredAt":"2026-10-22T00:00:00Z",
         "producer":"api","payload":{"type":"DEADLINE_D1","dedupKey":"NOTICE:%s:D1:2026-11-06",
         "target":{"type":"NOTICE","id":"%s"},"title":"내일 마감: 강동구 행복주택",
         "body":"관심 공고 접수가 내일(11월 6일) 마감돼요.","linkPath":"/notices/%s",
         "recipients":[{"userId":"%s","email":null,"quietEnabled":false}]}}
        """
        .formatted(eventId, eventType, eventId, eventId, eventId, UUID.randomUUID());
  }

  private static void await(Supplier<Boolean> condition) throws InterruptedException {
    Instant until = Instant.now().plus(WAIT);
    while (!condition.get()) {
      assertThat(Instant.now()).as("기다린 조건이 시간 안에 맞지 않았어요").isBefore(until);
      Thread.sleep(100);
    }
  }
}
