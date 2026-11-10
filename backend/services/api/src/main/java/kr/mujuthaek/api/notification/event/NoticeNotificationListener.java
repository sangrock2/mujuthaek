package kr.mujuthaek.api.notification.event;

import kr.mujuthaek.api.common.event.NoticePublished;
import kr.mujuthaek.api.common.event.NoticeUpdated;
import kr.mujuthaek.api.notification.service.internal.NoticeNotificationService;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * notice 내부 이벤트를 받아 알림 요청을 만들어요. BenefitNotificationListener와 같이 커밋 직전(BEFORE_COMMIT)에 받아서 공고 저장과
 * 알림 요청(아웃박스)이 한 트랜잭션이에요.
 */
@Component
class NoticeNotificationListener {

  private final NoticeNotificationService notifications;

  NoticeNotificationListener(NoticeNotificationService notifications) {
    this.notifications = notifications;
  }

  @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
  void on(NoticePublished event) {
    notifications.onPublished(event);
  }

  @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
  void on(NoticeUpdated event) {
    notifications.onUpdated(event);
  }
}
