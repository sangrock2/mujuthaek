package kr.mujuthaek.api.common.messaging;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import kr.mujuthaek.api.TestcontainersConfiguration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.AmqpAdmin;
import org.springframework.amqp.core.BindingBuilder;
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
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.annotation.DirtiesContext.MethodMode;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.rabbitmq.RabbitMQContainer;
import org.testcontainers.utility.DockerImageName;

/** 아웃박스가 실패 상황에서도 이벤트를 잃지 않고, 막힌 이벤트가 새 이벤트를 막지 않는지. */
@SpringBootTest(properties = "app.outbox.scheduling-enabled=false")
@Import({TestcontainersConfiguration.class, OutboxFailureTest.Rabbit.class})
class OutboxFailureTest {

  static final String QUEUE = "test.outbox.failure";
  static final String ROUTED = "test.failure.sent";
  static final String UNROUTED = "test.failure.nobody";

  @Autowired Outbox outbox;
  @Autowired OutboxRelay relay;
  @Autowired TransactionTemplate tx;
  @Autowired JdbcClient jdbc;
  @Autowired RabbitTemplate rabbit;
  @Autowired AmqpAdmin admin;
  @Autowired RabbitMQContainer rabbitmq;

  @BeforeEach
  void setUp() {
    jdbc.sql("delete from common.outbox").update();
    if (rabbitmq.isRunning()) {
      admin.declareQueue(new Queue(QUEUE, false));
      admin.declareBinding(
          BindingBuilder.bind(new Queue(QUEUE, false))
              .to(new TopicExchange(RabbitTopology.EVENTS, true, false))
              .with(ROUTED));
      admin.purgeQueue(QUEUE, false);
    }
  }

  @Test
  void stuckEventsDoNotStarveNewOnes() {
    // 받을 큐가 없는 이벤트가 한 번에 꺼내는 양(100)보다 많이 쌓여 있어도
    tx.executeWithoutResult(
        s -> {
          for (int i = 0; i < OutboxRelay.BATCH_SIZE + 5; i++) {
            outbox.add(UNROUTED, 1, Map.of("i", i));
          }
        });
    relay.relayOnce(); // 한 번씩 실패해서 attempts = 1
    tx.executeWithoutResult(s -> outbox.add(ROUTED, 1, Map.of("new", true)));

    relay.relayOnce();

    assertThat(rabbit.receive(QUEUE, 5_000)).as("새 이벤트가 나가야 해요").isNotNull();
  }

  @Test
  @DirtiesContext(methodMode = MethodMode.AFTER_METHOD) // 컨테이너를 멈추니 다음 테스트는 새로 띄워요
  void brokerDownKeepsEventsAndFailsFast() {
    tx.executeWithoutResult(s -> outbox.add(ROUTED, 1, Map.of("a", 1)));
    rabbitmq.stop();

    Instant start = Instant.now();
    assertThatThrownBy(relay::relayOnce).isInstanceOf(RuntimeException.class);
    Duration took = Duration.between(start, Instant.now());

    assertThat(took).as("브로커가 꺼져도 오래 붙잡고 있지 않아야 해요").isLessThan(Duration.ofSeconds(15));
    assertThat(
            jdbc.sql("select count(*) from common.outbox where published_at is null")
                .query(Long.class)
                .single())
        .isEqualTo(1L); // 이벤트는 남아서 다음에 다시 보내요
  }

  @Test
  void twoRelaysAtOnceSendEachEventOnce() throws Exception {
    int events = 150;
    tx.executeWithoutResult(
        s -> {
          for (int i = 0; i < events; i++) {
            outbox.add(ROUTED, 1, Map.of("i", i));
          }
        });

    // api 서버 두 대가 같은 순간 릴레이를 돌리는 것처럼
    var pool = java.util.concurrent.Executors.newFixedThreadPool(2);
    var start = new java.util.concurrent.CountDownLatch(1);
    java.util.concurrent.Callable<Integer> run =
        () -> {
          start.await();
          int total = 0;
          int sent;
          do {
            sent = relay.relayOnce();
            total += sent;
          } while (sent > 0);
          return total;
        };
    var a = pool.submit(run);
    var b = pool.submit(run);
    start.countDown();
    int sentTotal = a.get() + b.get();
    pool.shutdown();

    java.util.Set<String> ids = new java.util.HashSet<>();
    int received = 0;
    org.springframework.amqp.core.Message m;
    while ((m = rabbit.receive(QUEUE, 1_000)) != null) {
      received++;
      ids.add(m.getMessageProperties().getMessageId());
    }
    assertThat(sentTotal).isEqualTo(events);
    assertThat(received).as("두 번 나간 이벤트가 없어야 해요").isEqualTo(events);
    assertThat(ids).hasSize(events);
  }

  @Test
  void warnsOnlyOnFirstTenthHundredthAttempt() {
    assertThat(java.util.stream.IntStream.rangeClosed(1, 1000).filter(OutboxRelay::isLogWorthy))
        .containsExactly(1, 10, 100, 1000);
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
