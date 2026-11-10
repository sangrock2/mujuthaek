package kr.mujuthaek.api.common.messaging;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * 아웃박스에서 안 보낸 이벤트를 꺼내 RabbitMQ(mujuthaek.events)로 보내요. {@link OutboxRelayScheduler}가 1초마다 불러요.
 *
 * <p>브로커가 받았다고 답(publisher confirm)하고, 받을 큐가 있어서 되돌아오지 않은(returned) 것만 보낸 것으로 쳐요. 그 밖에는
 * published_at을 비워 두어 다음 차례에 다시 보내요. 실패한 줄이 뒤의 줄을 막지 않게, 실패해도 나머지는 계속 보내요.
 *
 * <p>보내기는 "최소 한 번"이에요. 보낸 직후 DB에 적기 전에 죽으면 같은 이벤트를 다시 보내요. 받는 쪽은 eventId로 한 번만 처리해요
 * (processed_events). 서버가 여러 대여도 같은 줄을 두 번 잡지 않게 for update skip locked로 가져와요.
 */
@Component
public class OutboxRelay {

  private static final Logger log = LoggerFactory.getLogger(OutboxRelay.class);

  static final int BATCH_SIZE = 100;
  static final Duration CONFIRM_TIMEOUT = Duration.ofSeconds(5);

  private final JdbcClient jdbc;
  private final RabbitTemplate rabbit;

  public OutboxRelay(JdbcClient jdbc, RabbitTemplate rabbit) {
    this.jdbc = jdbc;
    this.rabbit = rabbit;
  }

  /** 한 번 돌고 보낸 수를 돌려줘요 */
  @Transactional
  public int relayOnce() {
    List<Row> rows =
        jdbc.sql(
                """
                select event_id, event_type, attempts, payload::text as payload
                  from common.outbox
                 where published_at is null
                 order by attempts, created_at
                 limit :limit
                   for update skip locked
                """)
            .param("limit", BATCH_SIZE)
            .query(
                (rs, i) ->
                    new Row(
                        rs.getObject("event_id", UUID.class),
                        rs.getString("event_type"),
                        rs.getInt("attempts"),
                        rs.getString("payload")))
            .list();
    if (rows.isEmpty()) {
      return 0;
    }
    List<CorrelationData> pending = new ArrayList<>(rows.size());
    for (Row row : rows) {
      CorrelationData correlation = new CorrelationData(row.eventId().toString());
      rabbit.send(RabbitTopology.EVENTS, row.eventType(), message(row), correlation);
      pending.add(correlation);
    }
    List<UUID> sent = new ArrayList<>();
    List<UUID> failed = new ArrayList<>();
    long deadline =
        System.nanoTime() + CONFIRM_TIMEOUT.toNanos(); // 묶음 전체에 한 번: 브로커가 멈춰도 잠금을 오래 쥐지 않게
    for (int i = 0; i < rows.size(); i++) {
      Row row = rows.get(i);
      String problem = confirm(pending.get(i), deadline);
      if (problem == null) {
        sent.add(row.eventId());
      } else {
        failed.add(row.eventId());
        int attempts = row.attempts() + 1;
        if (isLogWorthy(attempts)) { // 계속 막힌 이벤트가 1초마다 경고를 쌓지 않게 1·10·100…번째만
          log.warn(
              "이벤트를 보내지 못해 다음에 다시 보내요: eventId={}, eventType={}, 이유={}, attempts={}",
              row.eventId(),
              row.eventType(),
              problem,
              attempts);
        }
      }
    }
    if (!sent.isEmpty()) {
      jdbc.sql(
              "update common.outbox set published_at = now(), attempts = attempts + 1 where event_id in (:ids)")
          .param("ids", sent)
          .update();
    }
    if (!failed.isEmpty()) {
      jdbc.sql("update common.outbox set attempts = attempts + 1 where event_id in (:ids)")
          .param("ids", failed)
          .update();
    }
    return sent.size();
  }

  static boolean isLogWorthy(int attempts) {
    while (attempts >= 10 && attempts % 10 == 0) {
      attempts /= 10;
    }
    return attempts == 1;
  }

  /** 문제가 없으면 null, 있으면 이유. deadline(System.nanoTime 기준)까지만 기다려요 */
  private static String confirm(CorrelationData correlation, long deadline) {
    try {
      long waitNanos = Math.max(0, deadline - System.nanoTime());
      CorrelationData.Confirm confirm =
          correlation.getFuture().get(waitNanos, TimeUnit.NANOSECONDS);
      if (!confirm.ack()) {
        return "브로커가 거부함 (" + confirm.reason() + ")";
      }
      if (correlation.getReturned() != null) {
        return "받을 큐가 없음 (" + correlation.getReturned().getReplyText() + ")";
      }
      return null;
    } catch (TimeoutException e) {
      return "브로커 응답 없음";
    } catch (ExecutionException e) {
      return "보내기 오류 (" + e.getCause().getClass().getSimpleName() + ")";
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      return "중단됨";
    }
  }

  private static Message message(Row row) {
    MessageProperties props = new MessageProperties();
    props.setContentType(MessageProperties.CONTENT_TYPE_JSON);
    props.setContentEncoding(StandardCharsets.UTF_8.name());
    props.setDeliveryMode(MessageDeliveryMode.PERSISTENT); // 브로커가 다시 시작해도 잃지 않게
    props.setMessageId(row.eventId().toString());
    props.setType(row.eventType());
    return new Message(row.payload().getBytes(StandardCharsets.UTF_8), props);
  }

  private record Row(UUID eventId, String eventType, int attempts, String payload) {}
}
