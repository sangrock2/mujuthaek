package kr.mujuthaek.api.notification.event;

import kr.mujuthaek.api.common.event.UserWithdrawn;
import kr.mujuthaek.api.notification.service.internal.InboxService;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/** 알림함 지우기: 탈퇴(UserWithdrawn)하면 그 회원 알림을 모두 (회원 삭제와 같은 트랜잭션), 매일 11:40(한국 시각)에 90일 지난 알림을. */
@Component
class InboxCleanup {

  private final InboxService inbox;

  InboxCleanup(InboxService inbox) {
    this.inbox = inbox;
  }

  @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
  void on(UserWithdrawn event) {
    inbox.deleteAll(event.userId());
  }

  /** notification.inbox-purge.enabled=false면 끄고(테스트) */
  @Configuration(proxyBeanMethods = false)
  @EnableScheduling
  @ConditionalOnProperty(name = "notification.inbox-purge.enabled", matchIfMissing = true)
  static class Purge {

    private final InboxService inbox;

    Purge(InboxService inbox) {
      this.inbox = inbox;
    }

    @Scheduled(cron = "0 40 11 * * *", zone = "Asia/Seoul") // 서버가 켜져 있는 시간(10시~)
    void run() {
      inbox.purgeExpired();
    }
  }
}
