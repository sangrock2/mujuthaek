package kr.mujuthaek.notification.delivery;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/** 발송 워커를 몇 초마다 깨워요. 테스트에서는 꺼 두고 {@link DeliveryWorker#runOnce()}를 직접 불러요. */
@Component
@ConditionalOnProperty(
    name = "notification.delivery.poll-enabled",
    havingValue = "true",
    matchIfMissing = true)
class DeliveryPoller {

  private final DeliveryWorker worker;

  DeliveryPoller(DeliveryWorker worker) {
    this.worker = worker;
  }

  @Scheduled(fixedDelayString = "${notification.delivery.poll-interval-ms:5000}")
  void poll() {
    int batch;
    do {
      batch = worker.runOnce();
    } while (batch > 0 && !Thread.currentThread().isInterrupted());
  }
}
