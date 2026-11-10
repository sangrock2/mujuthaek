package kr.mujuthaek.notification.event;

import java.util.ArrayList;
import java.util.List;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarable;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.boot.amqp.autoconfigure.RabbitListenerRetrySettingsCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * 알림 서버가 받는 이벤트 큐. 다른 서비스와 같은 exchange(mujuthaek.events)에 이 서버 전용 큐를 묶어요.
 *
 * <p>처리하지 못한 메시지는 재시도 없이 mujuthaek.dlx → {@link #DLQ}로 가요. 실패 큐 라우팅 키를 따로 줘서(notification.dead) 다른
 * 서비스의 실패 큐와 섞이지 않게 해요 (mujuthaek.dlx는 topic이라 원래 라우팅 키를 쓰면 같은 키로 묶인 다른 실패 큐에도 들어가요).
 */
@Configuration
public class EventQueueConfig {

  public static final String EXCHANGE = "mujuthaek.events";
  public static final String DLX = "mujuthaek.dlx";
  public static final String QUEUE = "mujuthaek.notification";
  public static final String DLQ = QUEUE + ".dlq";
  static final String DEAD_ROUTING_KEY = "notification.dead";

  /**
   * 받는 이벤트 (contracts/schemas/notification-events.draft.md). 모두 api가 보내요. 받을 사람·주소·문구는 api가 정해서
   * 보내고, 알림 서버는 보내기만 해요.
   */
  static final List<String> ROUTING_KEYS =
      List.of("notification.requested", "email.verification.requested", "user.withdrawn");

  @Bean
  Declarables notificationQueues() {
    TopicExchange events = new TopicExchange(EXCHANGE, true, false);
    TopicExchange dlx = new TopicExchange(DLX, true, false);
    Queue dlq = QueueBuilder.durable(DLQ).build();
    Queue queue =
        QueueBuilder.durable(QUEUE)
            .deadLetterExchange(DLX)
            .deadLetterRoutingKey(DEAD_ROUTING_KEY)
            .build();
    List<Declarable> declarables = new ArrayList<>();
    declarables.addAll(List.of(events, dlx, dlq, queue));
    declarables.add(BindingBuilder.bind(dlq).to(dlx).with(DEAD_ROUTING_KEY));
    ROUTING_KEYS.forEach(key -> declarables.add(BindingBuilder.bind(queue).to(events).with(key)));
    return new Declarables(declarables);
  }

  /**
   * 받기 재시도(application.yml spring.rabbitmq.listener.simple.retry)는 DB가 잠깐 끊기는 것 같은 오류에만 해요.
   * 봉투·payload가 계약에 맞지 않아 던진 AmqpRejectAndDontRequeueException은 다시 해도 같아서 바로 실패 큐로 보내요 (재시도하면 그동안
   * 큐가 막혀요).
   */
  @Bean
  RabbitListenerRetrySettingsCustomizer doNotRetryPermanentFailures() {
    return settings -> settings.setExceptionPredicate(EventQueueConfig::retryable);
  }

  static boolean retryable(Throwable error) {
    for (Throwable cause = error; cause != null; cause = cause.getCause()) {
      if (cause instanceof AmqpRejectAndDontRequeueException) {
        return false;
      }
    }
    return true;
  }
}
