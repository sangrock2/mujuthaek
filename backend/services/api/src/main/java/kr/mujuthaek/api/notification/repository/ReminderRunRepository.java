package kr.mujuthaek.api.notification.repository;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/** notification.reminder_runs: 하루 한 번 도는 알림 작업의 실행 기록. */
@Repository
public class ReminderRunRepository {

  private final JdbcClient jdbc;

  public ReminderRunRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  /**
   * 그날 작업을 맡아요 (트랜잭션 안에서). 처음 넣은 쪽만 true예요. 다른 서버가 같은 줄을 넣는 중이면 그 트랜잭션이 끝날 때까지 기다렸다가, 커밋됐으면 false,
   * 되돌려졌으면 이쪽이 넣고 true예요.
   */
  public boolean claim(LocalDate runDate, String kind, Instant now) {
    return jdbc.sql(
                """
                insert into notification.reminder_runs (run_date, kind, ran_at)
                values (:runDate, :kind, :now)
                on conflict (run_date, kind) do nothing
                """)
            .param("runDate", runDate)
            .param("kind", kind)
            .param("now", now.atOffset(ZoneOffset.UTC))
            .update()
        == 1;
  }

  public void finish(LocalDate runDate, String kind, int requested) {
    jdbc.sql(
            "update notification.reminder_runs set requested = :requested"
                + " where run_date = :runDate and kind = :kind")
        .param("requested", requested)
        .param("runDate", runDate)
        .param("kind", kind)
        .update();
  }
}
