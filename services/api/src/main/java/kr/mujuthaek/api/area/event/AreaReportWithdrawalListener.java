package kr.mujuthaek.api.area.event;

import kr.mujuthaek.api.area.service.AreaReportService;
import kr.mujuthaek.api.common.event.UserWithdrawn;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/** 회원이 탈퇴하면 그 회원의 생활권 제보를 지워요 (요구사항 3-16). 탈퇴와 같은 트랜잭션(커밋 직전)에서 지워 실패하면 탈퇴도 되돌려져요. */
@Component
class AreaReportWithdrawalListener {

  private final AreaReportService reports;

  AreaReportWithdrawalListener(AreaReportService reports) {
    this.reports = reports;
  }

  @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT, fallbackExecution = true)
  void on(UserWithdrawn event) {
    reports.forget(event.userId());
  }
}
