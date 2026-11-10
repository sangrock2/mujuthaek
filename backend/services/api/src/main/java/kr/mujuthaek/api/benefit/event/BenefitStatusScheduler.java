package kr.mujuthaek.api.benefit.event;

import kr.mujuthaek.api.benefit.service.internal.BenefitStatusService;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;

/**
 * 혜택 상태(접수 예정 → 접수 중 → 마감)를 매일 한국 시간 11시에 다시 계산해요. 운영 서버는 낮(10시~)에만 켜져 있어서, 서버가 뜬 뒤에도 한
 * 번(initial-delay 뒤) 계산해 꺼져 있던 동안 지난 날짜를 따라잡아요. benefit.status-refresh.enabled=false면 꺼요.
 */
@Configuration(proxyBeanMethods = false)
@EnableScheduling
@ConditionalOnProperty(name = "benefit.status-refresh.enabled", matchIfMissing = true)
class BenefitStatusScheduler {

  private final BenefitStatusService status;

  BenefitStatusScheduler(BenefitStatusService status) {
    this.status = status;
  }

  @Scheduled(cron = "0 0 11 * * *", zone = "Asia/Seoul")
  @Scheduled(
      initialDelayString = "${benefit.status-refresh.initial-delay:PT1M}",
      fixedDelayString = "P1D")
  void refresh() {
    status.refresh();
  }
}
