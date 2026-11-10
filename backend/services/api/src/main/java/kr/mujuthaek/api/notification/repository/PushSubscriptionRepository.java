package kr.mujuthaek.api.notification.repository;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.common.id.UuidV7;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/** notification.push_subscriptions: 웹 푸시 구독 기기. 기기마다 한 줄이에요. */
@Repository
public class PushSubscriptionRepository {

  private final JdbcClient jdbc;

  public PushSubscriptionRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  /** 알림 요청에 실을 기기 (주소·키 포함. 로그에 남기지 않아요) */
  public record SendableDevice(UUID userId, String endpoint, String p256dh, String auth) {
    @Override
    public String toString() {
      return "SendableDevice[userId=" + userId + ", ***]";
    }
  }

  /** 기기 목록에 보여 줄 칸만 (주소·키는 빼요) */
  public record Device(UUID id, String userAgent, Instant createdAt, Instant updatedAt) {}

  /** 이 주소를 지금 가진 회원. 같은 주소를 동시에 등록하는 요청이 겹치지 않게 그 줄을 잠가요 (트랜잭션 안에서) */
  public Optional<UUID> lockOwner(String endpoint) {
    return jdbc.sql(
            "select user_id from notification.push_subscriptions where endpoint = :endpoint for update")
        .param("endpoint", endpoint)
        .query(UUID.class)
        .optional();
  }

  /**
   * 기기를 넣거나 바꿔요. 이미 있는 주소면 키·이름·마지막 등록 시각을 바꾸고 회원도 이 회원으로 옮겨요. 다른 회원에게서 옮겨 오면 처음 등록 시각도 지금으로 바꿔요 (그
   * 회원에게는 새 기기라서).
   */
  public void upsert(
      UUID userId, String endpoint, String p256dh, String auth, String userAgent, Instant now) {
    jdbc.sql(
            """
            insert into notification.push_subscriptions
                (id, user_id, endpoint, p256dh, auth, user_agent, created_at, updated_at)
            values (:id, :userId, :endpoint, :p256dh, :auth, :userAgent, :now, :now)
            on conflict (endpoint) do update set
                user_id = excluded.user_id,
                p256dh = excluded.p256dh,
                auth = excluded.auth,
                user_agent = excluded.user_agent,
                created_at = case when push_subscriptions.user_id = excluded.user_id
                                  then push_subscriptions.created_at else excluded.created_at end,
                updated_at = excluded.updated_at
            """)
        .param("id", UuidV7.next())
        .param("userId", userId)
        .param("endpoint", endpoint)
        .param("p256dh", p256dh)
        .param("auth", auth)
        .param("userAgent", userAgent)
        .param("now", at(now))
        .update();
  }

  /** 최근에 등록한 {@code keep}대만 남기고 지워요. 지운 수를 돌려줘요 */
  public int keepLatest(UUID userId, int keep) {
    return jdbc.sql(
            """
            delete from notification.push_subscriptions
            where user_id = :userId
              and id not in (select id from notification.push_subscriptions
                             where user_id = :userId
                             order by updated_at desc, id desc
                             limit :keep)
            """)
        .param("userId", userId)
        .param("keep", keep)
        .update();
  }

  /** 이 회원의 그 주소만 지워요 (다른 회원 기기는 안 지움) */
  public int deleteByEndpoint(UUID userId, String endpoint) {
    return jdbc.sql(
            "delete from notification.push_subscriptions where user_id = :userId and endpoint = :endpoint")
        .param("userId", userId)
        .param("endpoint", endpoint)
        .update();
  }

  public int deleteById(UUID userId, UUID id) {
    return jdbc.sql(
            "delete from notification.push_subscriptions where user_id = :userId and id = :id")
        .param("userId", userId)
        .param("id", id)
        .update();
  }

  public int deleteAll(UUID userId) {
    return jdbc.sql("delete from notification.push_subscriptions where user_id = :userId")
        .param("userId", userId)
        .update();
  }

  /** 회원마다 최근에 등록한 {@code perUser}대까지. 회원·최근 순이에요 */
  public List<SendableDevice> findLatestForSend(Collection<UUID> userIds, int perUser) {
    if (userIds.isEmpty()) {
      return List.of();
    }
    return jdbc.sql(
            """
            select user_id, endpoint, p256dh, auth from (
                select user_id, endpoint, p256dh, auth,
                       row_number() over (partition by user_id order by updated_at desc, id desc) as n
                  from notification.push_subscriptions
                 where user_id in (:userIds)
            ) d
            where n <= :perUser
            order by user_id, n
            """)
        .param("userIds", userIds)
        .param("perUser", perUser)
        .query(
            (rs, i) ->
                new SendableDevice(
                    rs.getObject("user_id", UUID.class),
                    rs.getString("endpoint"),
                    rs.getString("p256dh"),
                    rs.getString("auth")))
        .list();
  }

  /** 최근에 쓴 기기부터 */
  public List<Device> findDevices(UUID userId) {
    return jdbc.sql(
            """
            select id, user_agent, created_at, updated_at from notification.push_subscriptions
            where user_id = :userId
            order by updated_at desc, id desc
            """)
        .param("userId", userId)
        .query(
            (rs, i) ->
                new Device(
                    rs.getObject("id", UUID.class),
                    rs.getString("user_agent"),
                    rs.getObject("created_at", OffsetDateTime.class).toInstant(),
                    rs.getObject("updated_at", OffsetDateTime.class).toInstant()))
        .list();
  }

  private static OffsetDateTime at(Instant instant) {
    return instant.atOffset(ZoneOffset.UTC);
  }
}
