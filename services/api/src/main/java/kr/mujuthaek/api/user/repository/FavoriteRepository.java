package kr.mujuthaek.api.user.repository;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/** account.favorites: 관심 공고·관심 정책. */
@Repository
public class FavoriteRepository {

  private final JdbcClient jdbc;

  public FavoriteRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  public record Favorite(String targetType, UUID targetId, Instant createdAt) {}

  /**
   * 같은 회원의 관심 저장을 줄 세워요(트랜잭션이 끝나면 풀려요). 「개수 세기 → 넣기」 사이에 다른 요청이 끼어들어 200개 제한을 넘던 것을 막아요 (2026-11-01
   * 동시성 시험: 199개에서 100개 동시 등록 → 최대 204개).
   */
  public void lockUser(UUID userId) {
    jdbc.sql("select pg_advisory_xact_lock(hashtextextended('favorites:' || cast(:id as text), 0))")
        .param("id", userId)
        .query((rs, i) -> 1)
        .list();
  }

  /** 이미 있으면 그대로 (처음 저장한 시각 유지). 새로 넣었으면 true */
  public boolean add(UUID userId, String targetType, UUID targetId, Instant now) {
    return jdbc.sql(
                """
                insert into account.favorites (user_id, target_type, target_id, created_at)
                values (:userId, :type, :id, :now)
                on conflict do nothing
                """)
            .param("userId", userId)
            .param("type", targetType)
            .param("id", targetId)
            .param("now", now.atOffset(ZoneOffset.UTC))
            .update()
        == 1;
  }

  /** 대상 ID들 중 저장한 줄을 모두 지워요 (합쳐진 공고는 합치기 전 ID로 저장된 줄도 있어요). */
  public int remove(UUID userId, String targetType, Collection<UUID> targetIds) {
    return jdbc.sql(
            "delete from account.favorites where user_id = :userId and target_type = :type and target_id in (:ids)")
        .param("userId", userId)
        .param("type", targetType)
        .param("ids", targetIds)
        .update();
  }

  /** 대상 ID들 중 하나라도 저장했는지. */
  public boolean exists(UUID userId, String targetType, Collection<UUID> targetIds) {
    return jdbc.sql(
                "select count(*) from account.favorites where user_id = :userId and target_type = :type and target_id in (:ids)")
            .param("userId", userId)
            .param("type", targetType)
            .param("ids", targetIds)
            .query(Long.class)
            .single()
        > 0;
  }

  public long count(UUID userId) {
    return jdbc.sql("select count(*) from account.favorites where user_id = :userId")
        .param("userId", userId)
        .query(Long.class)
        .single();
  }

  /** 최근 저장한 것부터. {@code afterAt}·{@code afterId}가 있으면 그 줄 다음부터. {@code targetType}이 null이면 모두 */
  public List<Favorite> page(
      UUID userId, String targetType, Instant afterAt, UUID afterId, int limit) {
    return jdbc.sql(
            """
            select target_type, target_id, created_at from account.favorites
             where user_id = :userId
               and (cast(:type as text) is null or target_type = :type)
               and (cast(:afterAt as timestamptz) is null or (created_at, target_id) < (:afterAt, :afterId))
             order by created_at desc, target_id desc
             limit :limit
            """)
        .param("userId", userId)
        .param("type", targetType, java.sql.Types.VARCHAR)
        .param(
            "afterAt",
            afterAt == null ? null : afterAt.atOffset(ZoneOffset.UTC),
            java.sql.Types.TIMESTAMP_WITH_TIMEZONE)
        .param("afterId", afterId, java.sql.Types.OTHER)
        .param("limit", limit)
        .query(
            (rs, i) ->
                new Favorite(
                    rs.getString("target_type"),
                    rs.getObject("target_id", UUID.class),
                    rs.getObject("created_at", OffsetDateTime.class).toInstant()))
        .list();
  }

  /** 이 공고·정책을 관심으로 둔 회원 (알림 대상자) */
  public List<UUID> userIds(String targetType, UUID targetId) {
    return jdbc.sql(
            "select user_id from account.favorites where target_type = :type and target_id = :id order by user_id")
        .param("type", targetType)
        .param("id", targetId)
        .query(UUID.class)
        .list();
  }
}
