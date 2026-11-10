package kr.mujuthaek.api.notification.event;

import kr.mujuthaek.api.notification.service.internal.DeadlineReminderService;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;

/**
 * 마감 D-3·D-1 알림을 확인해요. 정각 한 번(cron)이 아니라 10분마다 "오늘 09:00이 지났고 아직 안 했나"를 봐서, 09:00에 서버가 배포·재시작 중이었어도
 * 그날 안에 따라잡아요. notification.deadline-reminder.enabled=false면 끄고(테스트), 간격은
 * notification.deadline-reminder.delay로 바꿔요.
 */
@Configuration(proxyBeanMethods = false)
@EnableScheduling
@ConditionalOnProperty(name = "notification.deadline-reminder.enabled", matchIfMissing = true)
class DeadlineReminderScheduler {

  private final DeadlineReminderService reminders;

  DeadlineReminderScheduler(DeadlineReminderService reminders) {
    this.reminders = reminders;
  }

  @Scheduled(
      initialDelayString = "${notification.deadline-reminder.initial-delay:PT1M}",
      fixedDelayString = "${notification.deadline-reminder.delay:PT10M}")
  void check() {
    reminders.runIfDue();
  }
}
