package kr.mujuthaek.api.chat.repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.chat.domain.MessageStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

/** 채팅 메시지와 좋아요 (chat.messages, chat.message_likes). */
@Repository
public class ChatMessageRepository {

  /** 메시지 하나 + 답장 대상 미리보기 + 보는 사람이 좋아요했는지. */
  private static final String SELECT =
      """
      select m.id, m.notice_id, m.user_id, m.author_nickname, m.parent_id, m.content, m.like_count,
             m.report_count, m.status, m.created_at, p.author_nickname, p.content, p.status,
             exists(select 1 from chat.message_likes l
                    where l.message_id = m.id and l.user_id = cast(:viewer as uuid))
      from chat.messages m
      left join chat.messages p on p.id = m.parent_id
      """;

  private final NamedParameterJdbcTemplate jdbc;

  public ChatMessageRepository(JdbcTemplate jdbc) {
    this.jdbc = new NamedParameterJdbcTemplate(jdbc);
  }

  /**
   * @param userId 작성자
   * @param parentStatus 답장 대상의 상태 (답장이 아니거나, 원문이 작성자 탈퇴로 지워졌으면 null)
   * @param likedByViewer 보는 사람이 좋아요했는지 (보는 사람이 없으면 false)
   */
  public record MessageRow(
      UUID id,
      UUID noticeId,
      UUID userId,
      String authorNickname,
      UUID parentId,
      String content,
      int likeCount,
      int reportCount,
      MessageStatus status,
      OffsetDateTime createdAt,
      String parentNickname,
      String parentContent,
      MessageStatus parentStatus,
      boolean likedByViewer) {}

  /** 최근 보낸 메시지 수와 그중 가장 오래된 시각 (1분 5개 제한). */
  public record RecentSends(int count, OffsetDateTime oldest) {}

  public void insert(
      UUID id,
      UUID noticeId,
      UUID userId,
      String nickname,
      UUID parentId,
      String content,
      OffsetDateTime at) {
    jdbc.update(
        """
        insert into chat.messages (id, notice_id, user_id, author_nickname, parent_id, content, status,
                                   created_at)
        values (:id, :notice, :user, :nickname, :parent, :content, 'VISIBLE', :at)
        """,
        new MapSqlParameterSource()
            .addValue("id", id)
            .addValue("notice", noticeId)
            .addValue("user", userId)
            .addValue("nickname", nickname)
            .addValue("parent", parentId)
            .addValue("content", content)
            .addValue("at", at));
  }

  /**
   * @param viewer 좋아요 여부를 볼 회원 (없으면 null)
   */
  public Optional<MessageRow> find(UUID id, UUID viewer) {
    return jdbc
        .query(
            SELECT + " where m.id = :id",
            new MapSqlParameterSource().addValue("id", id).addValue("viewer", viewer),
            ChatMessageRepository::row)
        .stream()
        .findFirst();
  }

  /**
   * 방의 메시지를 최신순으로. before가 있으면 그 메시지보다 오래된 것만 (커서). noticeIds는 방 ID와 그 공고에 합쳐진 공고 ID들
   * (ChatRoom.noticeIds).
   */
  public List<MessageRow> page(List<UUID> noticeIds, UUID before, int limit, UUID viewer) {
    return jdbc.query(
        SELECT
            + """
             where m.notice_id in (:notices) and (cast(:before as uuid) is null or m.id < :before)
             order by m.id desc
             limit :limit
            """,
        new MapSqlParameterSource()
            .addValue("notices", noticeIds)
            .addValue("before", before)
            .addValue("limit", limit)
            .addValue("viewer", viewer),
        ChatMessageRepository::row);
  }

  /** SSE 재연결: after 다음에 만들어진 메시지를 오래된 순으로. noticeIds는 page와 같아요. */
  public List<MessageRow> after(List<UUID> noticeIds, UUID after, int limit) {
    return jdbc.query(
        SELECT
            + """
             where m.notice_id in (:notices) and m.id > :after
             order by m.id
             limit :limit
            """,
        new MapSqlParameterSource()
            .addValue("notices", noticeIds)
            .addValue("after", after)
            .addValue("limit", limit)
            .addValue("viewer", null),
        ChatMessageRepository::row);
  }

  /** 같은 회원의 보내기를 트랜잭션이 끝날 때까지 한 줄로 세워요 (동시에 보내도 1분 5개를 넘지 않게). */
  public void lockSender(UUID userId) {
    jdbc.queryForObject(
        "select 1 from pg_advisory_xact_lock(:key)",
        new MapSqlParameterSource(
            "key", userId.getMostSignificantBits() ^ userId.getLeastSignificantBits()),
        Integer.class);
  }

  public RecentSends recentSends(UUID userId, OffsetDateTime since) {
    return jdbc.queryForObject(
        """
        select count(*), min(created_at) from chat.messages
        where user_id = :user and created_at > :since
        """,
        new MapSqlParameterSource().addValue("user", userId).addValue("since", since),
        (rs, i) -> new RecentSends(rs.getInt(1), rs.getObject(2, OffsetDateTime.class)));
  }

  /** 소프트 삭제: 상태와 지운 시각만 바꾸고 본문은 신고 검토용으로 남겨요 (응답에서는 숨김). 이미 지운 메시지면 false. */
  public boolean markDeleted(UUID id, OffsetDateTime at) {
    return jdbc.update(
            """
            update chat.messages set status = 'DELETED', deleted_at = :at
            where id = :id and status <> 'DELETED'
            """,
            new MapSqlParameterSource().addValue("id", id).addValue("at", at))
        > 0;
  }

  /** 좋아요를 새로 눌렀으면 true (이미 눌렀으면 false). */
  public boolean addLike(UUID id, UUID userId, OffsetDateTime at) {
    return jdbc.update(
            """
            insert into chat.message_likes (message_id, user_id, created_at) values (:id, :user, :at)
            on conflict do nothing
            """,
            new MapSqlParameterSource()
                .addValue("id", id)
                .addValue("user", userId)
                .addValue("at", at))
        > 0;
  }

  /** 좋아요를 지웠으면 true (누른 적 없으면 false). */
  public boolean removeLike(UUID id, UUID userId) {
    return jdbc.update(
            "delete from chat.message_likes where message_id = :id and user_id = :user",
            new MapSqlParameterSource().addValue("id", id).addValue("user", userId))
        > 0;
  }

  /** 좋아요 수를 delta만큼 바꾸고 바뀐 수를 돌려줘요. */
  public int addLikeCount(UUID id, int delta) {
    return jdbc.queryForObject(
        "update chat.messages set like_count = like_count + :delta where id = :id returning like_count",
        new MapSqlParameterSource().addValue("id", id).addValue("delta", delta),
        Integer.class);
  }

  /**
   * 신고 수를 하나 올리고, 보이던 메시지가 검토 전 신고 limit건이 되면 가려요. 한 문장이라 동시에 신고가 들어와도 정확히 limit번째에서 가려져요.
   *
   * @return 바뀐 뒤 상태
   */
  public MessageStatus countReport(UUID id, int limit) {
    return MessageStatus.valueOf(
        jdbc.queryForObject(
            """
            update chat.messages
            set report_count = report_count + 1,
                status = case when status = 'VISIBLE' and report_count + 1 >= :limit
                              then 'HIDDEN_REPORTED' else status end
            where id = :id
            returning status
            """,
            new MapSqlParameterSource().addValue("id", id).addValue("limit", limit),
            String.class));
  }

  /**
   * 관리자 검토 결과를 메시지에 반영해요.
   *
   * @param resetReports true면 검토 전 신고 수를 0으로 (다시 보이게 할 때: 새 신고 3건이 쌓여야 다시 가려져요)
   */
  public void review(UUID id, MessageStatus status, boolean resetReports) {
    jdbc.update(
        """
        update chat.messages
        set status = :status, report_count = case when :reset then 0 else report_count end
        where id = :id
        """,
        new MapSqlParameterSource()
            .addValue("id", id)
            .addValue("status", status.name())
            .addValue("reset", resetReports));
  }

  /** 지운 메시지 하나 (방에 알리려고). */
  public record MessageRef(UUID id, UUID noticeId) {}

  /**
   * 탈퇴한 회원의 채팅 데이터 줄을 지워요 (다른 모듈처럼): 그 회원이 누른 좋아요(숫자도 줄여요), 남긴 신고(검토 전이면 신고 수도 줄여요), 쓴 메시지(달린
   * 좋아요·신고는 같이 지워져요). 다른 사람이 단 답장은 남아요.
   *
   * @return 지운 메시지
   */
  public List<MessageRef> forget(UUID userId) {
    var params = new MapSqlParameterSource("user", userId);
    jdbc.update(
        """
        update chat.messages m set like_count = m.like_count - 1
        where exists (select 1 from chat.message_likes l where l.message_id = m.id and l.user_id = :user)
        """,
        params);
    jdbc.update("delete from chat.message_likes where user_id = :user", params);
    jdbc.update(
        """
        update chat.messages m set report_count = m.report_count - 1
        where m.report_count > 0
          and exists (select 1 from chat.message_reports r
                      where r.message_id = m.id and r.reporter_id = :user and r.review_status = 'PENDING')
        """,
        params);
    jdbc.update("delete from chat.message_reports where reporter_id = :user", params);
    return jdbc.query(
        "delete from chat.messages where user_id = :user returning id, notice_id",
        params,
        (rs, i) -> new MessageRef(rs.getObject(1, UUID.class), rs.getObject(2, UUID.class)));
  }

  private static MessageRow row(ResultSet rs, int i) throws SQLException {
    String parentStatus = rs.getString(13);
    return new MessageRow(
        rs.getObject(1, UUID.class),
        rs.getObject(2, UUID.class),
        rs.getObject(3, UUID.class),
        rs.getString(4),
        rs.getObject(5, UUID.class),
        rs.getString(6),
        rs.getInt(7),
        rs.getInt(8),
        MessageStatus.valueOf(rs.getString(9)),
        rs.getObject(10, OffsetDateTime.class),
        rs.getString(11),
        rs.getString(12),
        parentStatus == null ? null : MessageStatus.valueOf(parentStatus),
        rs.getBoolean(14));
  }
}
