package kr.mujuthaek.api.area.repository;

import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.common.event.NoticeLocationsChanged;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.json.JsonMapper;

/** 공고 공개와 같은 트랜잭션으로 기록하는 위치 대기열. */
@Repository
public class NoticeLocationJobs {
  private final JdbcTemplate jdbc;
  private final JsonMapper json;

  public NoticeLocationJobs(JdbcTemplate jdbc, JsonMapper json) {
    this.jdbc = jdbc;
    this.json = json;
  }

  public record Job(NoticeLocationsChanged event, UUID token) {}

  @Transactional(propagation = Propagation.MANDATORY)
  public void enqueue(NoticeLocationsChanged event) {
    jdbc.update(
        """
        insert into area.notice_location_jobs as job (notice_id, notice_version, locations)
        values (?, ?, ?::jsonb)
        on conflict (notice_id) do update
          set notice_version = excluded.notice_version, locations = excluded.locations,
              run_at = now(), claim_token = null, failures = 0, finished_at = null, last_error = null
        where job.notice_version < excluded.notice_version
           or (job.notice_version = excluded.notice_version
               and (job.finished_at is not null or job.failures = 5))
        """,
        event.noticeId(),
        event.noticeVersion(),
        json.writeValueAsString(event.locations()));
  }

  public Optional<Job> claim() {
    UUID token = UUID.randomUUID();
    return jdbc
        .query(
            """
            with due as (
              select notice_id from area.notice_location_jobs
              where finished_at is null and failures < 5 and run_at <= now()
              order by run_at, notice_id limit 1 for update skip locked
            )
            update area.notice_location_jobs as job
               set claim_token = ?, run_at = now() + interval '5 minutes'
              from due where job.notice_id = due.notice_id
            returning job.notice_id, notice_version, locations::text
            """,
            (rs, index) ->
                new Job(
                    new NoticeLocationsChanged(
                        rs.getObject("notice_id", UUID.class),
                        rs.getInt("notice_version"),
                        List.copyOf(
                            Arrays.asList(
                                json.readValue(
                                    rs.getString("locations"),
                                    NoticeLocationsChanged.Location[].class)))),
                    token),
            token)
        .stream()
        .findFirst();
  }

  /** 외부 조회 사이에 소유권을 연장합니다. 새 공고 버전이 등록되면 이전 작업은 멈춥니다. */
  public boolean renew(Job job) {
    return jdbc.update(
            "update area.notice_location_jobs set run_at = now() + interval '5 minutes'"
                + " where notice_id = ? and claim_token = ?",
            job.event().noticeId(),
            job.token())
        == 1;
  }

  /** 공고 갱신과 순서가 같도록 공고 행을 먼저 잠급니다. 외부 호출이 없는 저장 단계에서만 부릅니다. */
  @Transactional(propagation = Propagation.MANDATORY)
  public boolean lockCurrent(Job job) {
    boolean current =
        jdbc.query(
            """
        select 1 from notice.notices
        where id = ? and current_version = ? and not hidden and merged_into is null
        for update
        """,
            rs -> (Boolean) rs.next(),
            job.event().noticeId(),
            job.event().noticeVersion());
    return current
        && jdbc.query(
            "select 1 from area.notice_location_jobs where notice_id = ? and claim_token = ? for update",
            rs -> (Boolean) rs.next(),
            job.event().noticeId(),
            job.token());
  }

  public void finish(Job job) {
    jdbc.update(
        "update area.notice_location_jobs set finished_at = now(), claim_token = null, last_error = null"
            + " where notice_id = ? and claim_token = ?",
        job.event().noticeId(),
        job.token());
  }

  public int retry(Job job, String error) {
    return jdbc.query(
        """
        update area.notice_location_jobs
           set claim_token = null, failures = failures + 1,
               run_at = now() + interval '30 seconds' * power(2, failures), last_error = ?
         where notice_id = ? and claim_token = ?
        returning failures
        """,
        rs -> rs.next() ? rs.getInt(1) : 0,
        error,
        job.event().noticeId(),
        job.token());
  }
}
