package kr.mujuthaek.api.user.event;

import kr.mujuthaek.api.common.event.PolicyHidden;
import kr.mujuthaek.api.user.service.FavoriteService;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/** 숨긴 중복 정책 사업에 둔 관심을 남은 사업으로 옮겨요. 숨김과 같은 트랜잭션(커밋 직전)이라, 옮기다 실패하면 숨김도 되돌려져요. */
@Component
class PolicyHiddenFavoriteListener {

  private final FavoriteService favorites;

  PolicyHiddenFavoriteListener(FavoriteService favorites) {
    this.favorites = favorites;
  }

  @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT, fallbackExecution = true)
  void on(PolicyHidden event) {
    favorites.moveToKeptPolicy(event.hiddenPolicyId(), event.keptPolicyId());
  }
}
