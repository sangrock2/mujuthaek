package kr.mujuthaek.api.user.repository;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.Collection;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class NotificationEmailRepository {
  private final JdbcClient jdbc;

  public NotificationEmailRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  public record Saved(
      UUID userId,
      String email,
      String tokenHash,
      Instant expiresAt,
      Instant requestedAt,
      LocalDate requestDay,
      int requestCount,
      Instant verifiedAt,
      boolean enabled,
      boolean newNotice,
      boolean deadline,
      boolean reportAnswer,
      String nonce) {
    public boolean allows(String type) {
      return enabled
          && verifiedAt != null
          && switch (type) {
            case "NEW_NOTICE", "NEW_SUPPORT" -> newNotice;
            case "DEADLINE_D3", "DEADLINE_D1" -> deadline;
            case "REPORT_ANSWERED" -> reportAnswer;
            default -> false;
          };
    }

    @Override
    public String toString() {
      return "NotificationEmail[userId=" + userId + "]";
    }
  }

  public void lock(UUID id) {
    jdbc.sql("select id from account.users where id=:u for update")
        .param("u", id)
        .query(UUID.class)
        .single();
  }

  public Optional<Saved> find(UUID id) {
    return jdbc.sql("select * from account.notification_emails where user_id=:u")
        .param("u", id)
        .query((rs, i) -> read(rs))
        .optional();
  }

  public Map<UUID, Saved> findAll(Collection<UUID> ids) {
    Map<UUID, Saved> out = new HashMap<>();
    var unique = java.util.List.copyOf(new java.util.LinkedHashSet<>(ids));
    for (int from = 0; from < unique.size(); from += 1000) {
      jdbc.sql("select * from account.notification_emails where user_id in (:ids)")
          .param("ids", unique.subList(from, Math.min(from + 1000, unique.size())))
          .query(
              rs -> {
                Saved s = read(rs);
                out.put(s.userId(), s);
              });
    }
    return out;
  }

  public void request(
      UUID id, String email, String hash, String nonce, Instant now, LocalDate day, int count) {
    jdbc.sql(
            """
        insert into account.notification_emails(user_id,email,token_hash,expires_at,requested_at,
          request_day,request_count,unsubscribe_nonce,collection_consent_version)
        values (:u,:email,:hash,:expires,:now,:day,:count,:nonce,'email-verification-v1')
        on conflict(user_id) do update set email=excluded.email,token_hash=excluded.token_hash,
          expires_at=excluded.expires_at,requested_at=excluded.requested_at,request_day=excluded.request_day,
          request_count=excluded.request_count,verified_at=null,enabled=false,new_notice=false,
          deadline=false,report_answer=false,consent_version=null,consented_at=null,revoked_at=:now,
          unsubscribe_nonce=excluded.unsubscribe_nonce,collection_consent_version=excluded.collection_consent_version
        """)
        .param("u", id)
        .param("email", email)
        .param("hash", hash)
        .param("nonce", nonce)
        .param("expires", now.plusSeconds(900).atOffset(ZoneOffset.UTC))
        .param("now", now.atOffset(ZoneOffset.UTC))
        .param("day", day)
        .param("count", count)
        .update();
  }

  public void verify(UUID id, Instant now) {
    jdbc.sql(
            "update account.notification_emails set verified_at=:now,token_hash=null,expires_at=null where user_id=:u")
        .param("u", id)
        .param("now", now.atOffset(ZoneOffset.UTC))
        .update();
  }

  public void settings(
      UUID id, boolean enabled, boolean notices, boolean deadline, boolean reports, Instant now) {
    jdbc.sql(
            """
        update account.notification_emails set enabled=:enabled,new_notice=:notices,deadline=:deadline,
          report_answer=:reports,consent_version=case when :enabled then 'email-notifications-v1' else consent_version end,
          consented_at=case when :enabled then :now else consented_at end,
          revoked_at=case when :enabled then null else :now end where user_id=:u
        """)
        .param("u", id)
        .param("enabled", enabled)
        .param("notices", notices)
        .param("deadline", deadline)
        .param("reports", reports)
        .param("now", now.atOffset(ZoneOffset.UTC))
        .update();
  }

  public void delete(UUID id) {
    // 주소를 지워도 재발송 횟수는 유지해 삭제·재등록으로 한도를 우회하지 못하게 해요.
    jdbc.sql(
            """
        update account.notification_emails set email=null,token_hash=null,expires_at=null,verified_at=null,
          enabled=false,new_notice=false,deadline=false,report_answer=false,consent_version=null,consented_at=null,collection_consent_version=null
        where user_id=:u
        """)
        .param("u", id)
        .update();
  }

  public java.util.List<UUID> preparing(UUID noticeId) {
    return jdbc.sql(
            "select user_id from account.application_preparations where notice_id=:notice and status='PREPARING'")
        .param("notice", noticeId)
        .query(UUID.class)
        .list();
  }

  public void expirePending(Instant before) {
    jdbc.sql(
            """
        update account.notification_emails set email=null,token_hash=null,expires_at=null,collection_consent_version=null
        where verified_at is null and email is not null and requested_at < :before
        """)
        .param("before", before.atOffset(ZoneOffset.UTC))
        .update();
  }

  private static Saved read(java.sql.ResultSet rs) throws java.sql.SQLException {
    return new Saved(
        rs.getObject("user_id", UUID.class),
        rs.getString("email"),
        rs.getString("token_hash"),
        instant(rs, "expires_at"),
        instant(rs, "requested_at"),
        rs.getObject("request_day", LocalDate.class),
        rs.getInt("request_count"),
        instant(rs, "verified_at"),
        rs.getBoolean("enabled"),
        rs.getBoolean("new_notice"),
        rs.getBoolean("deadline"),
        rs.getBoolean("report_answer"),
        rs.getString("unsubscribe_nonce"));
  }

  private static Instant instant(java.sql.ResultSet rs, String name) throws java.sql.SQLException {
    var value = rs.getTimestamp(name);
    return value == null ? null : value.toInstant();
  }
}
