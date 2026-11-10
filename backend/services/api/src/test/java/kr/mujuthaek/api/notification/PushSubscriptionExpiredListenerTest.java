package kr.mujuthaek.api.notification;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import java.util.function.BooleanSupplier;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.common.messaging.RabbitTopology;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.testcontainers.rabbitmq.RabbitMQContainer;
import org.testcontainers.utility.DockerImageName;

/** 알림 서버의 push.subscription.expired → 그 회원의 그 기기만 지움, 칸이 빠지면 실패 큐로. */
@SpringBootTest(properties = "app.outbox.scheduling-enabled=false")
@Import({TestcontainersConfiguration.class, PushSubscriptionExpiredListenerTest.Rabbit.class})
class PushSubscriptionExpiredListenerTest {

  static final Duration WAIT = Duration.ofSeconds(20);
  static final String DLQ = "mujuthaek.api.push-subscription-expired.dlq";

  @Autowired RabbitTemplate rabbit;
  @Autowired JdbcClient jdbc;

  @BeforeEach
  void clear() {
    jdbc.sql("delete from notification.push_subscriptions").update();
    while (rabbit.receive(DLQ) != null) {}
  }

  @Test
  void deletesOnlyThatMembersDevice() throws Exception {
    UUID me = UUID.randomUUID();
    UUID other = UUID.randomUUID();
    insert(me, "https://fcm.googleapis.com/fcm/send/dead");
    insert(me, "https://fcm.googleapis.com/fcm/send/alive");
    insert(other, "https://fcm.googleapis.com/fcm/send/moved"); // 그사이 다른 회원으로 옮겨진 기기

    String body = event(me, "https://fcm.googleapis.com/fcm/send/dead");
    publish(body);
    publish(body); // 같은 이벤트가 두 번 와도
    publish(event(me, "https://fcm.googleapis.com/fcm/send/moved"));

    await(() -> !exists("https://fcm.googleapis.com/fcm/send/dead"));
    Thread.sleep(1_000);
    assertThat(exists("https://fcm.googleapis.com/fcm/send/alive")).isTrue();
    assertThat(exists("https://fcm.googleapis.com/fcm/send/moved")).isTrue();
  }

  @Test
  void eventWithoutEndpointGoesToDeadLetterQueue() throws Exception {
    publish(event(UUID.randomUUID(), "").replace("\"endpoint\":\"\",", ""));

    Instant until = Instant.now().plus(WAIT);
    Message dead = null;
    while (dead == null && Instant.now().isBefore(until)) {
      dead = rabbit.receive(DLQ, 500);
    }
    assertThat(dead).isNotNull();
  }

  private static String event(UUID userId, String endpoint) {
    return """
        {"eventId":"%s","eventType":"push.subscription.expired","schemaVersion":1,
         "occurredAt":"2026-10-26T00:00:00Z","producer":"notification",
         "payload":{"userId":"%s","endpoint":"%s","status":410}}
        """
        .formatted(UUID.randomUUID(), userId, endpoint);
  }

  private void publish(String body) {
    MessageProperties props = new MessageProperties();
    props.setContentType(MessageProperties.CONTENT_TYPE_JSON);
    rabbit.send(
        RabbitTopology.EVENTS,
        "push.subscription.expired",
        new Message(body.getBytes(StandardCharsets.UTF_8), props));
  }

  private void insert(UUID userId, String endpoint) {
    jdbc.sql(
            """
            insert into notification.push_subscriptions (id, user_id, endpoint, p256dh, auth, created_at, updated_at)
            values (gen_random_uuid(), :u, :e, 'k', 'a', now(), now())
            """)
        .param("u", userId)
        .param("e", endpoint)
        .update();
  }

  private boolean exists(String endpoint) {
    return jdbc.sql("select count(*) from notification.push_subscriptions where endpoint = :e")
            .param("e", endpoint)
            .query(Long.class)
            .single()
        == 1;
  }

  private static void await(BooleanSupplier condition) throws InterruptedException {
    Instant until = Instant.now().plus(WAIT);
    while (!condition.getAsBoolean()) {
      assertThat(Instant.now()).as("기다린 조건이 시간 안에 맞지 않았어요").isBefore(until);
      Thread.sleep(100);
    }
  }

  @TestConfiguration(proxyBeanMethods = false)
  static class Rabbit {
    @Bean
    @ServiceConnection
    RabbitMQContainer rabbitmq() {
      return new RabbitMQContainer(DockerImageName.parse("rabbitmq:4.1-management"));
    }
  }
}
