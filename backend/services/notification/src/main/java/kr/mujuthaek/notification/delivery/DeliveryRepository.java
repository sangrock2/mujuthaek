package kr.mujuthaek.notification.delivery;

import java.sql.Types;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.notification.notification.NotificationType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/** deliveries 읽기·쓰기. 상태는 PENDING → SENT / FAILED 예요. 끝나면 받을 곳(address)을 지워요. */
@Repository
public class DeliveryRepository {

  private final JdbcClient jdbc;

  public DeliveryRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  /** 같은 회원·같은 알림·같은 채널 줄이 이미 있으면(같은 요청이 다시 옴) 넣지 않고 false */
  public boolean insert(NewDelivery d) {
    return jdbc.sql(
                """
                insert into deliveries (id, user_id, channel, address, type, dedup_key, title, body,
                                        link_path, inbox_id, digest, quiet, scheduled_at)
                values (:id, :userId, :channel, :address, :type, :dedupKey, :title, :body,
                        :linkPath, :inboxId, :digest, :quiet, :at)
                on conflict (dedup_key, channel) do nothing
                """)
            .param("id", d.id())
            .param("userId", d.userId())
            .param("channel", d.channel().name())
            .param("address", d.address())
            .param("type", d.type().name())
            .param("dedupKey", d.dedupKey())
            .param("title", d.title())
            .param("body", d.body())
            .param("linkPath", d.linkPath())
            .param("inboxId", d.inboxId(), Types.OTHER)
            .param("digest", d.digest())
            .param("quiet", d.quiet())
            .param("at", at(d.scheduledAt()))
            .update()
        == 1;
  }

  /**
   * 보낼 시각이 지난 묶음이 아닌 줄을 맡아요: {@code leaseUntil}까지 이 서버가 보낸다고 표시하고 돌려줘요 (짧은 트랜잭션 안에서 불러요). 서버가 여러
   * 대여도 같은 줄을 두 번 맡지 않고(for update skip locked), 맡은 서버가 죽으면 그 시각 뒤에 다시 맡을 수 있어요.
   */
  public List<DueDelivery> claimDueSingles(Instant now, int limit, Instant leaseUntil) {
    return jdbc
        .sql(
            """
            update deliveries set locked_until = :lease
             where id in (select id from deliveries
                           where status = 'PENDING' and not digest and scheduled_at <= :now
                             and (locked_until is null or locked_until <= :now)
                           order by scheduled_at, user_id
                           limit :limit
                             for update skip locked)
            returning id, user_id, channel, address, type, title, body, link_path, inbox_id, digest,
                      quiet, scheduled_at, attempts
            """)
        .param("now", at(now))
        .param("limit", limit)
        .param("lease", at(leaseUntil))
        .query(DeliveryRepository::due)
        .list()
        .stream()
        .sorted(
            java.util.Comparator.comparing(DueDelivery::scheduledAt).thenComparing(DueDelivery::id))
        .toList();
  }

  /**
   * 보낼 시각이 지난 묶음 단위 (회원·채널·주소·시각). 잠그지 않고 고르기만 해요. 웹 푸시는 요청마다 기기 목록이 다를 수 있어서(그사이 기기 등록·해제) 주소로 나누지
   * 않아요 (주소 null).
   */
  public List<DigestKey> dueDigestKeys(Instant now, int limit) {
    return jdbc.sql(
            """
            select user_id, channel, case when channel = 'PUSH' then null else address end as address,
                   scheduled_at
              from deliveries
             where status = 'PENDING' and digest and scheduled_at <= :now
               and (locked_until is null or locked_until <= :now)
             group by 1, 2, 3, 4
             order by scheduled_at, user_id
             limit :limit
            """)
        .param("now", at(now))
        .param("limit", limit)
        .query(
            (rs, i) ->
                new DigestKey(
                    rs.getObject("user_id", UUID.class),
                    Channel.valueOf(rs.getString("channel")),
                    rs.getString("address"),
                    rs.getObject("scheduled_at", OffsetDateTime.class).toInstant()))
        .list();
  }

  /**
   * 이 묶음을 이 서버가 맡아요 (트랜잭션이 끝날 때까지). 다른 서버가 맡고 있으면 false라 건너뛰어요. 묶음 줄은 맡은 서버만 잠가서, 같은 묶음이 두 통으로 나뉘지
   * 않아요.
   */
  public boolean tryLockDigest(DigestKey key) {
    return Boolean.TRUE.equals(
        jdbc.sql("select pg_try_advisory_xact_lock(hashtextextended(:key, 0))")
            .param("key", key.lockName())
            .query(Boolean.class)
            .single());
  }

  /**
   * 맡은 묶음의 줄을 모두 맡아요 ({@link #tryLockDigest} 뒤, 같은 트랜잭션). 다른 트랜잭션이 잠깐 잡고 있으면 놓을 때까지 기다려요 (빠지는 줄 없이
   * 한 통으로). 만든 순서(UUID v7)라 마지막 줄이 가장 최근 요청이에요.
   */
  public List<DueDelivery> claimDigestGroup(DigestKey key, Instant now, Instant leaseUntil) {
    return jdbc
        .sql(
            """
            update deliveries set locked_until = :lease
             where id in (select id from deliveries
                           where status = 'PENDING' and digest
                             and user_id = :userId and channel = :channel
                             and (cast(:address as text) is null or address = :address)
                             and scheduled_at = :at
                             and (locked_until is null or locked_until <= :now)
                             for update)
            returning id, user_id, channel, address, type, title, body, link_path, inbox_id, digest,
                      quiet, scheduled_at, attempts
            """)
        .param("userId", key.userId())
        .param("channel", key.channel().name())
        .param("address", key.address(), Types.VARCHAR)
        .param("at", at(key.scheduledAt()))
        .param("now", at(now))
        .param("lease", at(leaseUntil))
        .query(DeliveryRepository::due)
        .list()
        .stream()
        .sorted(java.util.Comparator.comparing(DueDelivery::id))
        .toList();
  }

  public void markSent(List<UUID> ids, String providerMessageId, Instant now) {
    jdbc.sql(
            """
            update deliveries
               set status = 'SENT', attempts = attempts + 1, provider_message_id = :messageId,
                   sent_at = :now, last_error = null, address = null, locked_until = null
             where id in (:ids)
            """)
        .param("ids", ids)
        .param("messageId", providerMessageId)
        .param("now", at(now))
        .update();
  }

  /** {@code address}가 있으면 받을 곳도 바꿔요 (못 보낸 기기만 남김). null이면 그대로 */
  public void markRetry(List<UUID> ids, String error, Instant retryAt, String address) {
    jdbc.sql(
            """
            update deliveries
               set attempts = attempts + 1, last_error = :error, scheduled_at = :at,
                   address = coalesce(cast(:address as text), address), locked_until = null
             where id in (:ids)
            """)
        .param("ids", ids)
        .param("error", error)
        .param("at", at(retryAt))
        .param("address", address, Types.VARCHAR)
        .update();
  }

  /** 다시 보내도 안 되거나 재시도를 다 썼어요. {@code attempted}면 이번에 보내 봤어요 */
  public void markFailed(List<UUID> ids, String error, boolean attempted) {
    jdbc.sql(
            """
            update deliveries
               set status = 'FAILED', last_error = :error, address = null, locked_until = null,
                   attempts = attempts + case when :attempted then 1 else 0 end
             where id in (:ids)
            """)
        .param("ids", ids)
        .param("error", error)
        .param("attempted", attempted)
        .update();
  }

  public void reschedule(List<UUID> ids, Instant at) {
    jdbc.sql("update deliveries set scheduled_at = :at, locked_until = null where id in (:ids)")
        .param("ids", ids)
        .param("at", at(at))
        .update();
  }

  private static DueDelivery due(java.sql.ResultSet rs, int row) throws java.sql.SQLException {
    return new DueDelivery(
        rs.getObject("id", UUID.class),
        rs.getObject("user_id", UUID.class),
        Channel.valueOf(rs.getString("channel")),
        rs.getString("address"),
        rs.getBoolean("digest"),
        rs.getBoolean("quiet"),
        rs.getObject("scheduled_at", OffsetDateTime.class).toInstant(),
        rs.getInt("attempts"),
        new OutgoingNotification(
            NotificationType.valueOf(rs.getString("type")),
            rs.getString("title"),
            rs.getString("body"),
            rs.getString("link_path"),
            rs.getObject("inbox_id", UUID.class)));
  }

  private static OffsetDateTime at(Instant instant) {
    return instant.atOffset(ZoneOffset.UTC);
  }

  /** 새로 만들 발송 줄 */
  public record NewDelivery(
      UUID id,
      UUID userId,
      Channel channel,
      String address,
      NotificationType type,
      String dedupKey,
      String title,
      String body,
      String linkPath,
      UUID inboxId,
      boolean digest,
      boolean quiet,
      Instant scheduledAt) {}

  /** 묶음 한 통의 단위. 웹 푸시는 address가 null이에요 (주소로 나누지 않음) */
  public record DigestKey(UUID userId, Channel channel, String address, Instant scheduledAt) {
    String lockName() {
      return "delivery-digest:" + userId + ":" + channel + ":" + address + ":" + scheduledAt;
    }
  }

  /** 보낼 차례가 된 발송 줄 1개 */
  public record DueDelivery(
      UUID id,
      UUID userId,
      Channel channel,
      String address,
      boolean digest,
      boolean quiet,
      Instant scheduledAt,
      int attempts,
      OutgoingNotification notification) {}
}
