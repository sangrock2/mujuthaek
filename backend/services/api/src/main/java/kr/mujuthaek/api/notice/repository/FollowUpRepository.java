package kr.mujuthaek.api.notice.repository;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.notice.domain.ReviewStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/** 공고에 붙인 후속 안내 (notice.notice_follow_ups). */
@Repository
public class FollowUpRepository {

  private final JdbcClient jdbc;

  public FollowUpRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  /** 이미 붙인 후속 안내 글. */
  public Optional<Attached> findByRawPost(UUID rawPostId) {
    return jdbc.sql(
            "select notice_id, raw_version, content_hash, review_status"
                + " from notice.notice_follow_ups where raw_post_id = :id")
        .param("id", rawPostId)
        .query(
            (rs, i) ->
                new Attached(
                    rs.getObject("notice_id", UUID.class),
                    rs.getInt("raw_version"),
                    rs.getString("content_hash"),
                    ReviewStatus.valueOf(rs.getString("review_status"))))
        .optional();
  }

  /** 붙이거나, 같은 글의 새 버전이면 내용을 바꿔요. */
  public void upsert(FollowUpRow row, Instant now) {
    jdbc.sql(
            "insert into notice.notice_follow_ups (raw_post_id, notice_id, raw_version,"
                + " source_event_id, title, detail_url, posted_on, schedules, content_hash,"
                + " review_status, original_notice_id, created_at, updated_at) values (:rawPostId,"
                + " :noticeId, :rawVersion, :eventId, :title, :detailUrl, :postedOn,"
                + " cast(:schedules as jsonb), :hash, :reviewStatus, :originalNoticeId, :now, :now)"
                + " on conflict (raw_post_id) do update set raw_version = excluded.raw_version,"
                + " source_event_id = excluded.source_event_id, title = excluded.title,"
                + " detail_url = excluded.detail_url, posted_on = excluded.posted_on,"
                + " schedules = excluded.schedules, content_hash = excluded.content_hash,"
                + " review_status = excluded.review_status, updated_at = excluded.updated_at")
        .param("rawPostId", row.rawPostId())
        .param("noticeId", row.noticeId())
        .param("rawVersion", row.rawVersion())
        .param("eventId", row.sourceEventId())
        .param("title", row.title())
        .param("detailUrl", row.detailUrl())
        .param("postedOn", row.postedOn())
        .param("schedules", row.schedulesJson())
        .param("hash", row.contentHash())
        .param("reviewStatus", row.reviewStatus().name())
        .param("originalNoticeId", row.originalNoticeId())
        .param("now", now.atOffset(ZoneOffset.UTC))
        .update();
  }

  /** 내용이 같은 승인본: 붙인 후속 안내의 검수 상태만 승인으로 올려요. */
  public void markApproved(UUID rawPostId, Instant now) {
    jdbc.sql(
            "update notice.notice_follow_ups set review_status = 'APPROVED', updated_at = :now"
                + " where raw_post_id = :id")
        .param("id", rawPostId)
        .param("now", now.atOffset(ZoneOffset.UTC))
        .update();
  }

  /** 공고를 합칠 때 후속 안내를 옮겨요. */
  public void moveToNotice(UUID from, UUID into, Instant now) {
    jdbc.sql(
            "update notice.notice_follow_ups set notice_id = :into, updated_at = :now"
                + " where notice_id = :from")
        .param("from", from)
        .param("into", into)
        .param("now", now.atOffset(ZoneOffset.UTC))
        .update();
  }

  /** 공고의 후속 안내. 게시일 순(모르면 뒤로). */
  public List<FollowUpView> findByNotice(UUID noticeId) {
    return jdbc.sql(
            "select title, detail_url, posted_on, schedules::text as schedules"
                + " from notice.notice_follow_ups where notice_id = :id"
                + " order by posted_on nulls last, created_at")
        .param("id", noticeId)
        .query(
            (rs, i) ->
                new FollowUpView(
                    rs.getString("title"),
                    rs.getString("detail_url"),
                    rs.getObject("posted_on", LocalDate.class),
                    rs.getString("schedules")))
        .list();
  }

  /** 공고에 가장 최근 붙이거나 바꾼 후속 안내 하나 (알림용). 후속 안내를 붙이는 트랜잭션 안에서 부르면 방금 붙인 글이에요(updated_at이 가장 늦어요). */
  public Optional<Latest> findLatestByNotice(UUID noticeId) {
    return jdbc.sql(
            "select raw_post_id, title, posted_on from notice.notice_follow_ups"
                + " where notice_id = :id order by updated_at desc, raw_post_id desc limit 1")
        .param("id", noticeId)
        .query(
            (rs, i) ->
                new Latest(
                    rs.getObject("raw_post_id", UUID.class),
                    rs.getString("title"),
                    rs.getObject("posted_on", LocalDate.class)))
        .optional();
  }

  public record Latest(UUID rawPostId, String title, LocalDate postedOn) {}

  public record Attached(
      UUID noticeId, int rawVersion, String contentHash, ReviewStatus reviewStatus) {}

  public record FollowUpRow(
      UUID rawPostId,
      UUID noticeId,
      int rawVersion,
      UUID sourceEventId,
      String title,
      String detailUrl,
      LocalDate postedOn,
      String schedulesJson,
      String contentHash,
      ReviewStatus reviewStatus,
      UUID originalNoticeId) {}

  public record FollowUpView(
      String title, String detailUrl, LocalDate postedOn, String schedulesJson) {}
}
