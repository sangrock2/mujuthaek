package kr.mujuthaek.api.area.repository;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.time.LocalDate;
import kr.mujuthaek.api.area.AreaTestDatabase;
import kr.mujuthaek.api.area.domain.AreaLoadRequest;
import kr.mujuthaek.api.area.domain.AreaSource;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

class AreaLoadQueueTest {

  private final JdbcTemplate jdbc = new JdbcTemplate(AreaTestDatabase.dataSource());
  private final AreaLoadQueue queue = new AreaLoadQueue(jdbc);

  @BeforeEach
  void clean() {
    jdbc.update("truncate area.load_runs");
  }

  @Test
  void claimNext_takesTheOldestWaitingRequest_once() {
    queue.request(request("11", "a"));
    queue.request(request("26", "b"));

    var first = queue.claimNext().orElseThrow();
    var second = queue.claimNext().orElseThrow();

    assertThat(first.request().scope()).isEqualTo("11");
    assertThat(first.attempts()).isEqualTo(1);
    assertThat(second.request().scope()).isEqualTo("26");
    assertThat(queue.claimNext()).isEmpty();
    assertThat(status(first)).isEqualTo("RUNNING");
  }

  @Test
  void release_waitsBeforeTryingAgain_thenFailsAfterMaxAttempts() {
    queue.request(request("11", "a"));
    var job = queue.claimNext().orElseThrow();

    assertThat(queue.release(job.runId(), job.attempts(), "S3 끊김", Duration.ofMinutes(1))).isTrue();
    assertThat(status(job)).isEqualTo("PENDING");
    assertThat(queue.claimNext()).as("1분 뒤에 다시 꺼내요").isEmpty();

    jdbc.update("update area.load_runs set next_attempt_at = now(), attempts = 2");
    var last = queue.claimNext().orElseThrow();
    assertThat(last.attempts()).isEqualTo(AreaLoadQueue.MAX_ATTEMPTS);
    assertThat(queue.release(last.runId(), last.attempts(), "S3 끊김", Duration.ZERO)).isFalse();
    assertThat(status(last)).isEqualTo("FAILED");
  }

  @Test
  void recoverStale_closesRunningRows_andQueuesThemAgainWhileAttemptsRemain() {
    queue.request(request("11", "a"));
    queue.request(request("26", "b"));
    queue.request(request("27", "c"));
    queue.claimNext();
    queue.claimNext();
    queue.claimNext();
    jdbc.update("update area.load_runs set attempts = 3 where load_scope = '26'");
    jdbc.update(
        "insert into area.load_runs (source, load_scope, file_key, file_sha256, data_date, status)"
            + " values ('ADDRESS_ENTRANCE', '27', 'k', ?, date '2026-09-30', 'SUCCEEDED')",
        "c".repeat(64));

    var recovered = queue.recoverStale("api가 멈췄어요");

    assertThat(recovered).hasSize(3);
    assertThat(
            jdbc.queryForObject(
                "select string_agg(load_scope || ':' || status, ',' order by load_scope, status)"
                    + " from area.load_runs",
                String.class))
        .isEqualTo("11:FAILED,11:PENDING,26:FAILED,27:FAILED,27:SUCCEEDED");
    assertThat(
            jdbc.queryForObject(
                "select attempts from area.load_runs where load_scope = '11' and status = 'PENDING'",
                Integer.class))
        .as("다시 넣어도 횟수는 이어서 세요")
        .isEqualTo(1);
  }

  private String status(AreaLoadQueue.Claimed job) {
    return jdbc.queryForObject(
        "select status from area.load_runs where id = ?", String.class, job.runId());
  }

  private static AreaLoadRequest request(String scope, String sha) {
    return new AreaLoadRequest(
        AreaSource.ADDRESS_ENTRANCE,
        scope,
        "area/ADDRESS_ENTRANCE/2026-09-30/" + scope + ".txt",
        sha.repeat(64),
        LocalDate.of(2026, 9, 30),
        false);
  }
}
