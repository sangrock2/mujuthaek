package kr.mujuthaek.api.notice.event;

import kr.mujuthaek.api.notice.service.internal.NoticeStatusService;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;

/**
 * 접수 상태 재계산을 주기적으로 돌려요. 상태가 바뀔 수 있는 시각(한국 시간 0시, 원문의 접수 시작·마감 시각)이 지난 공고만 다시 계산해서, 10분마다 확인하면 늦어도
 * 10분 안에 반영돼요. notice.status-refresh.enabled=false면 끄고(테스트), 간격은 notice.status-refresh.delay로 바꿔요.
 */
@Configuration(proxyBeanMethods = false)
@EnableScheduling
@ConditionalOnProperty(name = "notice.status-refresh.enabled", matchIfMissing = true)
class NoticeStatusScheduler {

  static final int BATCH = 200;

  private final NoticeStatusService status;

  NoticeStatusScheduler(NoticeStatusService status) {
    this.status = status;
  }

  @Scheduled(
      initialDelayString = "${notice.status-refresh.initial-delay:PT1M}",
      fixedDelayString = "${notice.status-refresh.delay:PT10M}")
  void refresh() {
    while (status.refreshDue(BATCH) == BATCH) {
      // 한 묶음이 꽉 찼으면 남은 공고가 있을 수 있어 이어서 처리해요
    }
  }
}
