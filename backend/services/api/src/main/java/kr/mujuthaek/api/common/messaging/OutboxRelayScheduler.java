package kr.mujuthaek.api.common.messaging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 아웃박스 발송과 정리를 정해진 때에 불러요. 테스트에서는 꺼 두고(app.outbox.scheduling-enabled=false) 직접 불러요.
 *
 * <p>RabbitMQ가 꺼져 있으면 보내기가 실패하고 이벤트는 아웃박스에 남아요. RabbitMQ가 다시 켜지면 그때 보내요. 스케줄링은 common의
 * SchedulingConfig가 켜요.
 */
@Component
@ConditionalOnProperty(
    name = "app.outbox.scheduling-enabled",
    havingValue = "true",
    matchIfMissing = true)
class OutboxRelayScheduler {

  private static final Logger log = LoggerFactory.getLogger(OutboxRelayScheduler.class);

  private final OutboxRelay relay;
  private final OutboxCleanup cleanup;

  OutboxRelayScheduler(OutboxRelay relay, OutboxCleanup cleanup) {
    this.relay = relay;
    this.cleanup = cleanup;
  }

  @Scheduled(fixedDelayString = "${app.outbox.relay-interval-ms:1000}")
  void relay() {
    try {
      int sent;
      do {
        sent = relay.relayOnce();
      } while (sent == OutboxRelay.BATCH_SIZE); // 꽉 찼으면 더 있을 수 있어요
    } catch (RuntimeException e) {
      log.warn("아웃박스 발송 실패, 다음 차례에 다시 해요: {}", e.getClass().getSimpleName());
    }
  }

  @Scheduled(cron = "0 20 11 * * *", zone = "Asia/Seoul") // 서버가 켜져 있는 시간(10시~)
  void cleanup() {
    cleanup.deletePublished();
  }
}
