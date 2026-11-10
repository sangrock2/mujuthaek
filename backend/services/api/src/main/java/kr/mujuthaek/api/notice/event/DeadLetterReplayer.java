package kr.mujuthaek.api.notice.event;

import com.rabbitmq.client.AMQP;
import com.rabbitmq.client.Channel;
import com.rabbitmq.client.GetResponse;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.connection.Connection;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.stereotype.Component;

/**
 * 실패 큐(mujuthaek.extraction.completed.dlq)의 메시지를 원래 큐로 다시 넣어요. 원인(DB 장애, 코드 오류)을 고친 뒤 운영자가 실행해요.
 *
 * <ul>
 *   <li>메시지를 원래 교환기·라우팅 키로 다시 보내고, 브로커가 받은 것을 확인(publisher confirm)한 뒤에 실패 큐에서 지워요. 중간에 끊겨도 메시지를 잃지
 *       않아요(중복은 processed_events가 막아요).
 *   <li>mandatory로 보내, 받을 큐가 없어(바인딩 누락) 브로커가 되돌려 보내면 확인(confirm)이 와도 지우지 않고 실패 큐에 그대로 두고 멈춰요.
 *   <li>다시 넣은 횟수를 헤더(x-mujuthaek-replays)에 세고, MAX_REPLAYS번 넘게 실패한 메시지는 실패 큐 끝으로 보내 사람이 보게 둬요.
 *   <li>실행 시점의 실패 큐 길이만큼만 읽어, 다시 실패해 돌아온 메시지를 같은 실행에서 또 읽지 않아요.
 * </ul>
 */
@Component
public class DeadLetterReplayer {

  private static final Logger log = LoggerFactory.getLogger(DeadLetterReplayer.class);
  static final String REPLAY_HEADER = "x-mujuthaek-replays";
  static final int MAX_REPLAYS = 3;
  private static final long CONFIRM_TIMEOUT_MS = 10_000;

  /** 실행 결과. replayed: 원래 큐로 보냄, parked: 횟수 초과로 실패 큐 끝에 둠. */
  public record Result(int replayed, int parked) {}

  private final ConnectionFactory connectionFactory;

  public DeadLetterReplayer(ConnectionFactory connectionFactory) {
    this.connectionFactory = connectionFactory;
  }

  public Result replay(int limit) {
    try (Connection connection = connectionFactory.createConnection();
        Channel channel = connection.createChannel(false)) {
      channel.confirmSelect();
      // 받을 큐가 없는 메시지는 브로커가 basic.return으로 돌려보낸 뒤 확인(ack)을 보내요. 확인만 보고 지우면 메시지를 잃어요
      AtomicBoolean returned = new AtomicBoolean();
      channel.addReturnListener(r -> returned.set(true));
      long waiting = channel.messageCount(ExtractionCompletedListener.DLQ);
      int replayed = 0;
      int parked = 0;
      for (long i = 0; i < Math.min(limit, waiting); i++) {
        GetResponse message = channel.basicGet(ExtractionCompletedListener.DLQ, false);
        if (message == null) {
          break;
        }
        AMQP.BasicProperties props = message.getProps();
        int replays = replays(props);
        if (replays >= MAX_REPLAYS) {
          channel.basicPublish("", ExtractionCompletedListener.DLQ, true, props, message.getBody());
          parked++;
        } else {
          Map<String, Object> headers =
              props.getHeaders() == null ? new HashMap<>() : new HashMap<>(props.getHeaders());
          headers.put(REPLAY_HEADER, replays + 1);
          channel.basicPublish(
              "", // 기본 교환기 + 큐 이름: 이 큐에만 다시 넣어요(리뷰 2026-10-22)
              ExtractionCompletedListener.QUEUE,
              true,
              props.builder().headers(headers).build(),
              message.getBody());
          replayed++;
        }
        channel.waitForConfirmsOrDie(CONFIRM_TIMEOUT_MS);
        if (returned.getAndSet(false)) {
          channel.basicNack(message.getEnvelope().getDeliveryTag(), false, true);
          throw new IllegalStateException("받을 큐가 없어 브로커가 메시지를 돌려보냈어요 (교환기·큐 연결 확인 필요)");
        }
        channel.basicAck(message.getEnvelope().getDeliveryTag(), false);
      }
      log.info("실패 큐 다시 넣기: 원래 큐로 {}건, 횟수 초과로 남김 {}건", replayed, parked);
      return new Result(replayed, parked);
    } catch (Exception e) {
      throw new IllegalStateException("실패 큐 메시지를 다시 넣지 못했어요", e);
    }
  }

  static int replays(AMQP.BasicProperties props) {
    Object value = props.getHeaders() == null ? null : props.getHeaders().get(REPLAY_HEADER);
    return value instanceof Number number ? number.intValue() : 0;
  }
}
