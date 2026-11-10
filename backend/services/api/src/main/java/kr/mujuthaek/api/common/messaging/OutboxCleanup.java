package kr.mujuthaek.api.common.messaging;

import java.time.Clock;
import java.time.Duration;
import java.time.ZoneOffset;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;

/** 보낸 지 하루 지난 아웃박스 줄을 지워요. 이메일 주소·인증 코드가 실린 이벤트가 있어서 오래 두지 않아요. 안 보낸 줄은 남겨요. */
@Component
public class OutboxCleanup {

  private static final Logger log = LoggerFactory.getLogger(OutboxCleanup.class);

  static final Duration RETENTION = Duration.ofDays(1);
  static final int BATCH = 1_000;

  private final JdbcClient jdbc;
  private final Clock clock;

  public OutboxCleanup(JdbcClient jdbc, Clock clock) {
    this.jdbc = jdbc;
    this.clock = clock;
  }

  /** 지운 줄 수를 돌려줘요. 1,000줄씩 나눠 지워요 */
  public int deletePublished() {
    var cutoff = clock.instant().minus(RETENTION).atOffset(ZoneOffset.UTC);
    int total = 0;
    int deleted;
    do {
      deleted =
          jdbc.sql(
                  """
                  delete from common.outbox where event_id in (
                    select event_id from common.outbox
                     where published_at is not null and published_at < :cutoff
                     limit :batch)
                  """)
              .param("cutoff", cutoff)
              .param("batch", BATCH)
              .update();
      total += deleted;
    } while (deleted == BATCH);
    if (total > 0) {
      log.info("보낸 아웃박스 줄 지움: {}", total);
    }
    return total;
  }
}
