package kr.mujuthaek.api.notification.event;

import kr.mujuthaek.api.common.event.ReportAnswered;
import kr.mujuthaek.api.notification.service.internal.ReportAnsweredNotificationService;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * 공고·혜택·창업 사업·생활권 제보의 답변 이벤트(ReportAnswered 네 종류)를 받아 제보한 회원에게 알림 요청을 만들어요. 커밋 직전(BEFORE_COMMIT)에
 * 받아서 제보 처리와 알림 요청(아웃박스)이 한 트랜잭션이에요.
 */
@Component
class ReportAnsweredListener {

  private final ReportAnsweredNotificationService notifications;

  ReportAnsweredListener(ReportAnsweredNotificationService notifications) {
    this.notifications = notifications;
  }

  @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
  void on(ReportAnswered event) {
    notifications.onAnswered(event);
  }
}
