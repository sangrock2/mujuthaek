package kr.mujuthaek.api.common.messaging;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.api.TestcontainersConfiguration;
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
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.rabbitmq.RabbitMQContainer;
import org.testcontainers.utility.DockerImageName;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** 아웃박스에 적기(같은 트랜잭션) → RabbitMQ로 보내기 → 보낸 줄 정리. */
@SpringBootTest(properties = "app.outbox.scheduling-enabled=false")
@Import({TestcontainersConfiguration.class, OutboxTest.Rabbit.class})
class OutboxTest {

  static final String QUEUE = "test.outbox";
  static final String ROUTED = "test.outbox.sent"; // 테스트 큐에 묶인 라우팅 키
  static final String UNROUTED = "test.outbox.nobody"; // 받을 큐가 없는 라우팅 키

  @Autowired Outbox outbox;
  @Autowired OutboxRelay relay;
  @Autowired OutboxCleanup cleanup;
  @Autowired TransactionTemplate tx;
  @Autowired JdbcClient jdbc;
  @Autowired RabbitTemplate rabbit;
  @Autowired AmqpAdmin admin;
  @Autowired JsonMapper json;

  @BeforeEach
  void setUp() {
    jdbc.sql("delete from common.outbox").update();
    admin.declareQueue(new Queue(QUEUE, false));
    admin.declareBinding(
        BindingBuilder.bind(new Queue(QUEUE, false))
            .to(new TopicExchange(RabbitTopology.EVENTS, true, false))
            .with(ROUTED));
    admin.purgeQueue(QUEUE, false);
  }

  @Test
  void addNeedsTheCallersTransaction() {
    assertThatThrownBy(() -> outbox.add(ROUTED, 1, Map.of("a", 1)))
        .isInstanceOf(IllegalTransactionStateException.class);
  }

  @Test
  void rolledBackSaveLeavesNoEvent() {
    tx.executeWithoutResult(
        status -> {
          outbox.add(ROUTED, 1, Map.of("a", 1));
          status.setRollbackOnly(); // 저장이 실패한 것처럼
        });

    assertThat(count("true")).isZero();
  }

  @Test
  void committedEventIsSentWithEnvelope() throws Exception {
    UUID eventId = tx.execute(s -> outbox.add(ROUTED, 1, Map.of("userId", "U1")));

    assertThat(relay.relayOnce()).isEqualTo(1);

    Message message = rabbit.receive(QUEUE, 5_000);
    assertThat(message).isNotNull();
    assertThat(message.getMessageProperties().getMessageId()).isEqualTo(eventId.toString());
    JsonNode envelope = json.readTree(new String(message.getBody(), StandardCharsets.UTF_8));
    assertThat(envelope.path("eventId").asString()).isEqualTo(eventId.toString());
    assertThat(envelope.path("eventType").asString()).isEqualTo(ROUTED);
    assertThat(envelope.path("schemaVersion").asInt()).isEqualTo(1);
    assertThat(envelope.path("producer").asString()).isEqualTo("api");
    assertThat(envelope.path("occurredAt").asString()).endsWith("Z");
    assertThat(envelope.path("payload").path("userId").asString()).isEqualTo("U1");
    assertThat(eventId.version()).isEqualTo(7);
    assertThat(count("published_at is not null")).isEqualTo(1);
    assertThat(relay.relayOnce()).isZero(); // 다시 보내지 않아요
  }

  @Test
  void unroutableEventStaysAndDoesNotBlockOthers() {
    tx.executeWithoutResult(s -> outbox.add(UNROUTED, 1, Map.of("a", 1)));
    tx.executeWithoutResult(s -> outbox.add(ROUTED, 1, Map.of("b", 2)));

    assertThat(relay.relayOnce()).isEqualTo(1);

    assertThat(rabbit.receive(QUEUE, 5_000)).isNotNull();
    assertThat(
            jdbc.sql(
                    "select attempts from common.outbox where event_type = :t and published_at is null")
                .param("t", UNROUTED)
                .query(Integer.class)
                .single())
        .isEqualTo(1); // 남아서 다음 차례에 다시 보내요
  }

  @Test
  void cleanupDeletesOnlyEventsSentMoreThanADayAgo() {
    tx.executeWithoutResult(
        s -> {
          outbox.add(ROUTED, 1, Map.of("old", true));
          outbox.add(ROUTED, 1, Map.of("recent", true));
          outbox.add(UNROUTED, 1, Map.of("unsent", true));
        });
    jdbc.sql(
            """
            update common.outbox set published_at = case
              when payload->'payload'->>'old' is not null then now() - interval '2 days'
              when payload->'payload'->>'recent' is not null then now() - interval '1 hour' end
             where event_type = :t
            """)
        .param("t", ROUTED)
        .update();

    assertThat(cleanup.deletePublished()).isEqualTo(1);
    assertThat(count("true")).isEqualTo(2);
  }

  private long count(String where) {
    return jdbc.sql("select count(*) from common.outbox where " + where).query(Long.class).single();
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
