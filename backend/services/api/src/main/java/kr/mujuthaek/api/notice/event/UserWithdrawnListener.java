package kr.mujuthaek.api.notice.event;

import kr.mujuthaek.api.common.event.UserWithdrawn;
import kr.mujuthaek.api.notice.service.internal.NoticeReportService;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * 회원이 탈퇴하면 그 회원의 공고 제보를 지워요 (요구사항 3-16: 탈퇴 후 데이터 0건). 탈퇴와 같은 트랜잭션(커밋 직전)에서 지워, 지우다 실패하면 탈퇴도 되돌려져 다시
 * 할 수 있어요. 예전엔 커밋 뒤에 한 번만 돌고 실패를 삼켜 제보가 영구히 남을 수 있었어요(2026-11-10 코드 검토).
 */
@Component
class UserWithdrawnListener {

  private final NoticeReportService reports;

  UserWithdrawnListener(NoticeReportService reports) {
    this.reports = reports;
  }

  @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT, fallbackExecution = true)
  void on(UserWithdrawn event) {
    reports.forget(event.userId());
  }
}
