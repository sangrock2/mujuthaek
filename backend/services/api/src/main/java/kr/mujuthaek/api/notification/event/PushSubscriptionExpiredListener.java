package kr.mujuthaek.api.notification.event;

import java.util.UUID;
import kr.mujuthaek.api.common.messaging.EventInbox;
import kr.mujuthaek.api.common.messaging.RabbitTopology;
import kr.mujuthaek.api.notification.service.internal.PushSubscriptionService;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;

/**
 * 알림 서버가 보내는 push.subscription.expired를 받아 그 기기 구독을 지워요 (contracts/schemas/web-push.draft.md 5장).
 * 푸시 서비스가 404·410(앱 삭제·권한 끔·만료)을 준 기기라 다음 알림 요청부터 빼요.
 *
 * <p>큐 mujuthaek.api.push-subscription-expired(+ .dlq)는 api가 만들어요 (알림 서버의 받는 큐
 * mujuthaek.notification과 다른 큐). 같은 eventId는 한 번만 처리하고, 칸이 빠진 메시지는 실패 큐로 보내요.
 */
@Component
class PushSubscriptionExpiredListener {

  static final String QUEUE = "mujuthaek.api.push-subscription-expired";
  static final String EVENT_TYPE = "push.subscription.expired";

  private final EventInbox inbox;
  private final PushSubscriptionService subscriptions;

  PushSubscriptionExpiredListener(EventInbox inbox, PushSubscriptionService subscriptions) {
    this.inbox = inbox;
    this.subscriptions = subscriptions;
  }

  @RabbitListener(queues = QUEUE)
  void on(Message message) {
    inbox.handleOnce(
        message,
        EVENT_TYPE,
        1,
        Expired.class,
        e -> {
          if (e.userId() == null || e.endpoint() == null || e.endpoint().isBlank()) {
            throw new AmqpRejectAndDontRequeueException("userId·endpoint가 없어요");
          }
          subscriptions.removeExpired(e.userId(), e.endpoint(), e.status());
        });
  }

  /** 주소는 로그에 남기지 않아요 (toString 가림) */
  record Expired(UUID userId, String endpoint, Integer status) {
    @Override
    public String toString() {
      return "Expired[userId=" + userId + ", status=" + status + "]";
    }
  }

  @Configuration
  static class Queues {

    @Bean
    Declarables pushSubscriptionExpiredQueue() {
      return RabbitTopology.queue(QUEUE, EVENT_TYPE);
    }
  }
}
