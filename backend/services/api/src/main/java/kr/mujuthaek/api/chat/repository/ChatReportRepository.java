package kr.mujuthaek.api.chat.repository;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.chat.domain.MessageStatus;
import kr.mujuthaek.api.chat.domain.ReportReason;
import kr.mujuthaek.api.chat.domain.ReviewStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

/** 메시지 신고 (chat.message_reports). */
@Repository
public class ChatReportRepository {

  private final NamedParameterJdbcTemplate jdbc;

  public ChatReportRepository(JdbcTemplate jdbc) {
    this.jdbc = new NamedParameterJdbcTemplate(jdbc);
  }

  /** 관리자 목록의 신고 한 줄 + 신고된 메시지. */
  public record ReportRow(
      UUID id,
      UUID messageId,
      ReportReason reason,
      String detail,
      ReviewStatus reviewStatus,
      OffsetDateTime createdAt,
      UUID noticeId,
      String authorNickname,
      String content,
      MessageStatus messageStatus,
      int reportCount,
      UUID reviewedBy,
      OffsetDateTime reviewedAt) {}

  /** 신고를 저장했으면 true. 같은 회원이 이미 신고한 메시지면 false. */
  public boolean insert(
      UUID id,
      UUID messageId,
      UUID reporterId,
      ReportReason reason,
      String detail,
      OffsetDateTime at) {
    return jdbc.update(
            """
            insert into chat.message_reports (id, message_id, reporter_id, reason, detail, review_status,
                                              created_at)
            values (:id, :message, :reporter, :reason, :detail, 'PENDING', :at)
            on conflict (message_id, reporter_id) do nothing
            """,
            new MapSqlParameterSource()
                .addValue("id", id)
                .addValue("message", messageId)
                .addValue("reporter", reporterId)
                .addValue("reason", reason.name())
                .addValue("detail", detail)
                .addValue("at", at))
        > 0;
  }

  /** 메시지의 검토 전 신고를 모두 검토 결과로 바꾸고 처리한 관리자·시각을 남겨요. */
  public void review(UUID messageId, ReviewStatus result, UUID reviewer, OffsetDateTime at) {
    jdbc.update(
        """
        update chat.message_reports set review_status = :result, reviewed_by = :reviewer,
                                        reviewed_at = :at
        where message_id = :message and review_status = 'PENDING'
        """,
        new MapSqlParameterSource()
            .addValue("message", messageId)
            .addValue("result", result.name())
            .addValue("reviewer", reviewer)
            .addValue("at", at));
  }

  /** 검토 전 신고가 걸린 글 수 (관리자 사이드바 숫자). review_status 인덱스로 세요. */
  public int pendingMessages() {
    Integer n =
        jdbc.queryForObject(
            "select count(distinct message_id) from chat.message_reports where review_status = 'PENDING'",
            new MapSqlParameterSource(),
            Integer.class);
    return n == null ? 0 : n;
  }

  /** 검토 상태별 신고를 최신순으로. before가 있으면 그 신고보다 오래된 것만 (커서). */
  public List<ReportRow> page(ReviewStatus status, UUID before, int limit) {
    return jdbc.query(
        """
        select r.id, r.message_id, r.reason, r.detail, r.review_status, r.created_at,
               m.notice_id, m.author_nickname, m.content, m.status, m.report_count,
               r.reviewed_by, r.reviewed_at
        from chat.message_reports r
        join chat.messages m on m.id = r.message_id
        where r.review_status = :status and (cast(:before as uuid) is null or r.id < :before)
        order by r.id desc
        limit :limit
        """,
        new MapSqlParameterSource()
            .addValue("status", status.name())
            .addValue("before", before)
            .addValue("limit", limit),
        (rs, i) ->
            new ReportRow(
                rs.getObject(1, UUID.class),
                rs.getObject(2, UUID.class),
                ReportReason.valueOf(rs.getString(3)),
                rs.getString(4),
                ReviewStatus.valueOf(rs.getString(5)),
                rs.getObject(6, OffsetDateTime.class),
                rs.getObject(7, UUID.class),
                rs.getString(8),
                rs.getString(9),
                MessageStatus.valueOf(rs.getString(10)),
                rs.getInt(11),
                rs.getObject(12, UUID.class),
                rs.getObject(13, OffsetDateTime.class)));
  }
}
