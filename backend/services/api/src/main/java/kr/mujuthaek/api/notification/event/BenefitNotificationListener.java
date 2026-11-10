package kr.mujuthaek.api.notification.event;

import kr.mujuthaek.api.common.event.BenefitPublished;
import kr.mujuthaek.api.common.event.BenefitUpdated;
import kr.mujuthaek.api.notification.service.internal.BenefitNotificationService;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * benefit 내부 이벤트를 받아 알림 요청을 만들어요. 커밋 직전(BEFORE_COMMIT)에 받아서 정책 저장과 알림 요청(아웃박스)이 한 트랜잭션이에요. 커밋 뒤에
 * 받으면 그 사이 api가 죽을 때 알림 요청이 사라져요.
 */
@Component
class BenefitNotificationListener {

  private final BenefitNotificationService notifications;

  BenefitNotificationListener(BenefitNotificationService notifications) {
    this.notifications = notifications;
  }

  @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
  void on(BenefitPublished event) {
    notifications.onPublished(event);
  }

  @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
  void on(BenefitUpdated event) {
    notifications.onUpdated(event);
  }
}
