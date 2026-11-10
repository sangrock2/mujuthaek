package kr.mujuthaek.api.notification.event;

import kr.mujuthaek.api.common.event.UserWithdrawn;
import kr.mujuthaek.api.notification.service.internal.PushSubscriptionService;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * 회원 탈퇴(UserWithdrawn)면 그 회원의 웹 푸시 기기를 모두 지워요. 구독 테이블은 회원 테이블과 FK가 없어서 여기서 지워요. 회원 삭제와 같은
 * 트랜잭션(BEFORE_COMMIT)이라 삭제가 되돌려지면 기기도 남아요.
 */
@Component
class PushSubscriptionCleanup {

  private final PushSubscriptionService subscriptions;

  PushSubscriptionCleanup(PushSubscriptionService subscriptions) {
    this.subscriptions = subscriptions;
  }

  @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
  void on(UserWithdrawn event) {
    subscriptions.unsubscribeAll(event.userId());
  }
}
