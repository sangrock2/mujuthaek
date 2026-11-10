package kr.mujuthaek.api.notification.event;

import kr.mujuthaek.api.common.event.PolicyPublished;
import kr.mujuthaek.api.common.event.PolicyUpdated;
import kr.mujuthaek.api.notification.service.internal.PolicyNotificationService;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * notice의 정책(창업지원 사업·사업공간 모집) 내부 이벤트를 받아 알림 요청을 만들어요. 커밋 직전(BEFORE_COMMIT)에 받아서 정책 저장과 알림 요청(아웃박스)이
 * 한 트랜잭션이에요.
 */
@Component
class PolicyNotificationListener {

  private final PolicyNotificationService notifications;

  PolicyNotificationListener(PolicyNotificationService notifications) {
    this.notifications = notifications;
  }

  @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
  void on(PolicyPublished event) {
    notifications.onPublished(event);
  }

  @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
  void on(PolicyUpdated event) {
    notifications.onUpdated(event);
  }
}
