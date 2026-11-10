package kr.mujuthaek.notification.outbox;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.notification.TestcontainersConfiguration;
import kr.mujuthaek.notification.event.EventQueueConfig;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.AmqpAdmin;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** 아웃박스 → RabbitMQ: 받을 큐가 있으면 보내고 표시, 없으면 남겨 두었다가 다시. 보낸 지 하루 지난 줄 정리. */
@SpringBootTest(
    properties = {
      "notification.delivery.poll-enabled=false",
      "notification.outbox.scheduling-enabled=false"
    })
@Import(TestcontainersConfiguration.class)
class OutboxRelayTest {

  static final String TEST_QUEUE = "test.push.subscription.expired";

  @Autowired Outbox outbox;
  @Autowired OutboxRelay relay;
  @Autowired RabbitTemplate rabbit;
  @Autowired AmqpAdmin admin;
  @Autowired JdbcClient jdbc;
  @Autowired TransactionTemplate tx;
  @Autowired JsonMapper json;

  @BeforeEach
  void clear() {
    jdbc.sql("delete from outbox").update();
    admin.deleteQueue(TEST_QUEUE);
  }

  @Test
  void publishesWhenAQueueListensAndKeepsItOtherwise() {
    UUID userId = UUID.randomUUID();
    UUID eventId =
        tx.execute(
            s ->
                outbox.add(
                    "push.subscription.expired",
                    1,
                    Map.of(
                        "userId",
                        userId,
                        "endpoint",
                        "https://fcm.googleapis.com/x",
                        "status",
                        410)));

    assertThat(relay.relayOnce()).as("아직 받을 큐가 없음 (api가 안 떴음)").isZero();
    assertThat(attempts(eventId)).isEqualTo(1);

    Queue queue = new Queue(TEST_QUEUE, false, false, true);
    admin.declareQueue(queue);
    admin.declareBinding(
        BindingBuilder.bind(queue)
            .to(new TopicExchange(EventQueueConfig.EXCHANGE, true, false))
            .with("push.subscription.expired"));

    assertThat(relay.relayOnce()).isEqualTo(1);
    Message message = rabbit.receive(TEST_QUEUE, 5_000);
    assertThat(message).isNotNull();
    JsonNode envelope = json.readTree(new String(message.getBody(), StandardCharsets.UTF_8));
    assertThat(envelope.path("eventType").asString()).isEqualTo("push.subscription.expired");
    assertThat(envelope.path("producer").asString()).isEqualTo("notification");
    assertThat(envelope.path("payload").path("userId").asString()).isEqualTo(userId.toString());
    assertThat(envelope.path("payload").path("status").asInt()).isEqualTo(410);
    assertThat(message.getMessageProperties().getMessageId()).isEqualTo(eventId.toString());
    assertThat(relay.relayOnce()).as("한 번 보낸 것은 다시 안 보냄").isZero();
  }

  @Test
  void deletesRowsPublishedMoreThanADayAgo() {
    jdbc.sql(
            """
            insert into outbox (event_id, event_type, schema_version, payload, published_at)
            values (gen_random_uuid(), 'x', 1, '{}', now() - interval '25 hours'),
                   (gen_random_uuid(), 'x', 1, '{}', now() - interval '1 hour'),
                   (gen_random_uuid(), 'x', 1, '{}', null)
            """)
        .update();

    assertThat(relay.deletePublished()).isEqualTo(1);
    assertThat(jdbc.sql("select count(*) from outbox").query(Long.class).single()).isEqualTo(2L);
  }

  @Test
  void onlyEveryPowerOfTenFailureIsLogged() {
    assertThat(OutboxRelay.isLogWorthy(1)).isTrue();
    assertThat(OutboxRelay.isLogWorthy(10)).isTrue();
    assertThat(OutboxRelay.isLogWorthy(100)).isTrue();
    assertThat(OutboxRelay.isLogWorthy(2)).isFalse();
    assertThat(OutboxRelay.isLogWorthy(20)).isFalse();
  }

  private int attempts(UUID eventId) {
    return jdbc.sql("select attempts from outbox where event_id = :id")
        .param("id", eventId)
        .query(Integer.class)
        .single();
  }
}
