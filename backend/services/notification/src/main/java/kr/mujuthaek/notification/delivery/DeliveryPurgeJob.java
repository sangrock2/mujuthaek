package kr.mujuthaek.notification.delivery;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 오래된 기록 정리. 매일 11:30(Asia/Seoul, 운영 서버가 낮에만 켜져 있어서)에 90일 지난 발송 줄(deliveries), 받은 이벤트
 * 장부(processed_events), 탈퇴 회원 기록 (withdrawn_users)을 지워요.
 *
 * <p>아직 보내지 않은 줄(PENDING)은 남겨요. 한 번에 많이 지우면 잠금이 길어져서 1,000줄씩 나눠 지워요 (한 묶음이 한 트랜잭션).
 */
@Component
public class DeliveryPurgeJob {

  private static final Logger log = LoggerFactory.getLogger(DeliveryPurgeJob.class);

  static final Duration RETENTION = Duration.ofDays(90);
  static final int BATCH = 1_000;

  private final JdbcClient jdbc;
  private final Clock clock;

  public DeliveryPurgeJob(JdbcClient jdbc, Clock clock) {
    this.jdbc = jdbc;
    this.clock = clock;
  }

  @Scheduled(cron = "0 30 11 * * *", zone = "Asia/Seoul") // 서버가 켜져 있는 시간(10시~)
  public void run() {
    Instant cutoff = clock.instant().minus(RETENTION);
    int deliveries =
        purge(
            """
            delete from deliveries where id in (
              select id from deliveries
               where created_at < :cutoff and status <> 'PENDING'
               limit :batch)
            """,
            cutoff);
    int events =
        purge(
            """
            delete from processed_events where event_id in (
              select event_id from processed_events where processed_at < :cutoff limit :batch)
            """,
            cutoff);
    int withdrawn =
        purge(
            """
            delete from withdrawn_users where user_id in (
              select user_id from withdrawn_users where withdrawn_at < :cutoff limit :batch)
            """,
            cutoff);
    log.info(
        "오래된 기록 지움: deliveries={}, processed_events={}, withdrawn_users={}",
        deliveries,
        events,
        withdrawn);
  }

  private int purge(String sql, Instant cutoff) {
    int total = 0;
    int deleted;
    do {
      deleted =
          jdbc.sql(sql)
              .param("cutoff", cutoff.atOffset(ZoneOffset.UTC))
              .param("batch", BATCH)
              .update();
      total += deleted;
    } while (deleted == BATCH);
    return total;
  }
}
