package kr.mujuthaek.api.area.repository;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.common.event.NoticeLocationsChanged;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.postgresql.PostgreSQLContainer;
import tools.jackson.databind.json.JsonMapper;

class NoticeLocationJobsPostgresTest {
  private static PostgreSQLContainer postgres;
  private static JdbcTemplate jdbc;
  private static TransactionTemplate transaction;
  private static final JsonMapper JSON = JsonMapper.builder().build();
  private final UUID id = UUID.randomUUID();
  private NoticeLocationJobs jobs;

  @BeforeAll
  static void setupDatabase() throws Exception {
    String port = System.getenv("MUJUTHAEK_LOCATION_TEST_DB_PORT");
    DriverManagerDataSource dataSource;
    if (port == null) {
      postgres = new PostgreSQLContainer("postgres:17.6-alpine");
      postgres.start();
      dataSource =
          new DriverManagerDataSource(
              postgres.getJdbcUrl(), postgres.getUsername(), postgres.getPassword());
    } else {
      dataSource =
          new DriverManagerDataSource(
              "jdbc:postgresql://127.0.0.1:" + Integer.parseInt(port) + "/location_jobs_test",
              "postgres",
              "");
    }
    jdbc = new JdbcTemplate(dataSource);
    transaction = new TransactionTemplate(new DataSourceTransactionManager(dataSource));
    jdbc.execute("create schema if not exists notice; create schema if not exists area");
    jdbc.execute(
        """
        create table if not exists notice.notices (
          id uuid primary key, current_version int not null, hidden boolean default false,
          merged_into uuid
        )
        """);
    jdbc.execute("drop table if exists area.notice_location_jobs");
    try (var migration =
        NoticeLocationJobsPostgresTest.class.getResourceAsStream(
            "/db/migration/V202611201500__area_notice_location_jobs.sql")) {
      jdbc.execute(new String(migration.readAllBytes(), StandardCharsets.UTF_8));
    }
  }

  @AfterAll
  static void stopDatabase() {
    if (postgres != null) {
      postgres.stop();
    }
  }

  @BeforeEach
  void reset() {
    jdbc.execute("truncate notice.notices, area.notice_location_jobs");
    jobs = new NoticeLocationJobs(jdbc, JSON);
  }

  @Test
  void publicationAndItsLocationJobRollBackTogether() {
    transaction.executeWithoutResult(
        status -> {
          publish(1, event(1));
          status.setRollbackOnly();
        });
    assertThat(jdbc.queryForObject("select count(*) from notice.notices", Integer.class)).isZero();
    assertThat(jobs.claim()).isEmpty();
  }

  @Test
  void aNewWorkerCanReclaimAnInterruptedJobAndOldTokenCannotFinishIt() {
    transaction.executeWithoutResult(status -> publish(1, event(1)));
    var old = jobs.claim().orElseThrow();
    assertThat(old.event()).isEqualTo(event(1));
    assertThat(jobs.claim()).isEmpty();
    expire();

    var restarted = new NoticeLocationJobs(jdbc, JSON);
    var renewed = restarted.claim().orElseThrow();
    assertThat(renewed.token()).isNotEqualTo(old.token());
    assertThat(jobs.renew(old)).isFalse();
    jobs.finish(old);
    transaction.executeWithoutResult(
        status -> {
          assertThat(restarted.lockCurrent(renewed)).isTrue();
          restarted.finish(renewed);
        });
    assertThat(restarted.claim()).isEmpty();
  }

  @Test
  void aNewVersionFencesInFlightWorkAndCanRemoveAllLocations() {
    transaction.executeWithoutResult(status -> publish(1, event(1)));
    var old = jobs.claim().orElseThrow();
    var empty = new NoticeLocationsChanged(id, 2, List.of());
    transaction.executeWithoutResult(status -> publish(2, empty));
    transaction.executeWithoutResult(status -> jobs.enqueue(event(1)));

    transaction.executeWithoutResult(status -> assertThat(jobs.lockCurrent(old)).isFalse());
    var newer = jobs.claim().orElseThrow();
    assertThat(newer.event()).isEqualTo(empty);
    assertThat(jobs.renew(old)).isFalse();
  }

  @Test
  void failedJobUsesBackoffAndCanBeExplicitlyRequeued() {
    transaction.executeWithoutResult(status -> publish(1, event(1)));
    for (int attempt = 1; attempt <= 5; attempt++) {
      var job = jobs.claim().orElseThrow();
      assertThat(jobs.retry(job, "Failure")).isEqualTo(attempt);
      assertThat(jobs.claim()).isEmpty();
      expire();
    }
    assertThat(jobs.claim()).isEmpty();
    transaction.executeWithoutResult(status -> jobs.enqueue(event(1)));
    assertThat(jobs.claim()).isPresent();
  }

  private NoticeLocationsChanged event(int version) {
    return new NoticeLocationsChanged(
        id,
        version,
        List.of(
            new NoticeLocationsChanged.Location(
                "site", "COMPLEX", "1111000000", "가상로 1", "가상 단지")));
  }

  private void publish(int version, NoticeLocationsChanged event) {
    jdbc.update(
        """
        insert into notice.notices(id, current_version) values (?, ?)
        on conflict (id) do update set current_version = excluded.current_version
        """,
        id,
        version);
    jobs.enqueue(event);
  }

  private void expire() {
    jdbc.update(
        "update area.notice_location_jobs set run_at = now() - interval '1 second' where notice_id = ?",
        id);
  }
}
