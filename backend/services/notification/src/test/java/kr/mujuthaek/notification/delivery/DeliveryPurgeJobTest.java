package kr.mujuthaek.notification.delivery;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.notification.TestcontainersConfiguration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.simple.JdbcClient;

/** 90일 지난 발송 줄·이벤트 장부는 지우고, 그 안의 것과 아직 안 보낸 줄은 남겨요. */
@SpringBootTest(properties = "notification.delivery.poll-enabled=false")
@Import({TestcontainersConfiguration.class, DeliveryFlowTest.Fakes.class})
class DeliveryPurgeJobTest {

  @Autowired DeliveryPurgeJob job;
  @Autowired JdbcClient jdbc;
  @Autowired DeliveryFlowTest.MutableClock clock;

  @BeforeEach
  void setUp() {
    jdbc.sql("delete from deliveries").update();
    jdbc.sql("delete from withdrawn_users").update();
    jdbc.sql("delete from processed_events").update();
    clock.set("2026-10-23T04:00");
  }

  @Test
  void deletesOnlyOldFinishedRows() {
    delivery("SENT-91", "SENT", 91);
    delivery("FAILED-91", "FAILED", 91);
    delivery("PENDING-91", "PENDING", 91); // 아직 안 보냄
    delivery("SENT-89", "SENT", 89);
    event(91);
    event(89);

    job.run();

    assertThat(jdbc.sql("select title from deliveries order by title").query(String.class).list())
        .isEqualTo(List.of("PENDING-91", "SENT-89"));
    assertThat(jdbc.sql("select count(*) from processed_events").query(Long.class).single())
        .isEqualTo(1L);
  }

  @Test
  void withdrawnMembersAreForgottenAfterNinetyDays() {
    for (int days : new int[] {91, 89}) {
      jdbc.sql(
              "insert into withdrawn_users (user_id, withdrawn_at) values (gen_random_uuid(), :at)")
          .param(
              "at",
              clock
                  .instant()
                  .minus(java.time.Duration.ofDays(days))
                  .atOffset(java.time.ZoneOffset.UTC))
          .update();
    }

    job.run();

    assertThat(jdbc.sql("select count(*) from withdrawn_users").query(Long.class).single())
        .isEqualTo(1L);
  }

  @Test
  void deletesMoreThanOneBatch() {
    int rows = DeliveryPurgeJob.BATCH + 5;
    jdbc.sql(
            """
            insert into deliveries (id, user_id, channel, type, dedup_key, title, body, link_path,
                                    status, scheduled_at, created_at)
            select gen_random_uuid(), gen_random_uuid(), 'EMAIL', 'CORRECTED', 'k' || g, 't', 'b', '/n',
                   'SENT', :at, :at
              from generate_series(1, :rows) g
            """)
        .param("at", daysAgo(100))
        .param("rows", rows)
        .update();

    job.run();

    assertThat(jdbc.sql("select count(*) from deliveries").query(Long.class).single()).isZero();
  }

  private void delivery(String title, String status, int days) {
    jdbc.sql(
            """
            insert into deliveries (id, user_id, channel, type, dedup_key, title, body, link_path,
                                    status, scheduled_at, created_at)
            values (:id, :user, 'EMAIL', 'CORRECTED', :key, :title, 'b', '/n', :status, :at, :at)
            """)
        .param("id", UUID.randomUUID())
        .param("user", UUID.randomUUID())
        .param("key", title)
        .param("title", title)
        .param("status", status)
        .param("at", daysAgo(days))
        .update();
  }

  private void event(int days) {
    jdbc.sql(
            "insert into processed_events (event_id, event_type, processed_at) values (:id, 'x', :at)")
        .param("id", UUID.randomUUID())
        .param("at", daysAgo(days))
        .update();
  }

  private OffsetDateTime daysAgo(int days) {
    return clock.instant().minus(Duration.ofDays(days)).atOffset(ZoneOffset.UTC);
  }
}
