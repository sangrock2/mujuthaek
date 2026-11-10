package kr.mujuthaek.api.user.repository;

import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/** account.notification_settings: 알림 종류별 켬·끔과 조용한 시간. 줄이 없으면 기본값(모두 켬, 조용한 시간 끔)이에요. */
@Repository
public class NotificationSettingRepository {

  private final JdbcClient jdbc;

  public NotificationSettingRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  public record Settings(
      boolean newNotice,
      boolean newSupport,
      boolean deadline,
      boolean correction,
      boolean followUp,
      boolean quietEnabled) {

    public static final Settings DEFAULT = new Settings(true, true, true, true, true, false);
  }

  public Optional<Settings> find(UUID userId) {
    return jdbc.sql(
            """
            select new_notice, new_support, deadline, correction, follow_up, quiet_enabled
              from account.notification_settings where user_id = :u
            """)
        .param("u", userId)
        .query((rs, i) -> settings(rs))
        .optional();
  }

  /** 한 번에 묻는 회원 수. IN 목록 하나에 모두 넣으면 6만 5천여 명부터 바인드 변수 한도를 넘어 알림이 통째로 실패했어요. */
  static final int CHUNK = 1000;

  /**
   * 줄이 있는 회원만 담아요 (없으면 기본값으로 보세요). CHUNK명씩 나눠 물어요(2026-11-10 코드 검토: 전국 대상 새 공고처럼 대상이 많으면 쿼리가 실패해
   * 아무에게도 가지 않았음, NoticeQueryService.findSummaries와 같은 방식).
   */
  public Map<UUID, Settings> findAll(Collection<UUID> userIds) {
    Map<UUID, Settings> out = new HashMap<>();
    List<UUID> ids = List.copyOf(new java.util.LinkedHashSet<>(userIds));
    for (int from = 0; from < ids.size(); from += CHUNK) {
      jdbc.sql(
              """
              select user_id, new_notice, new_support, deadline, correction, follow_up, quiet_enabled
                from account.notification_settings where user_id in (:ids)
              """)
          .param("ids", ids.subList(from, Math.min(ids.size(), from + CHUNK)))
          .query(
              rs -> {
                out.put(rs.getObject("user_id", UUID.class), settings(rs));
              });
    }
    return out;
  }

  public void save(UUID userId, Settings s, Instant now) {
    jdbc.sql(
            """
            insert into account.notification_settings
                (user_id, new_notice, new_support, deadline, correction, follow_up, quiet_enabled, updated_at)
            values (:u, :newNotice, :newSupport, :deadline, :correction, :followUp, :quiet, :now)
            on conflict (user_id) do update set new_notice = excluded.new_notice,
                new_support = excluded.new_support, deadline = excluded.deadline,
                correction = excluded.correction, follow_up = excluded.follow_up,
                quiet_enabled = excluded.quiet_enabled, updated_at = excluded.updated_at
            """)
        .param("u", userId)
        .param("newNotice", s.newNotice())
        .param("newSupport", s.newSupport())
        .param("deadline", s.deadline())
        .param("correction", s.correction())
        .param("followUp", s.followUp())
        .param("quiet", s.quietEnabled())
        .param("now", now.atOffset(ZoneOffset.UTC))
        .update();
  }

  private static Settings settings(java.sql.ResultSet rs) throws java.sql.SQLException {
    return new Settings(
        rs.getBoolean("new_notice"),
        rs.getBoolean("new_support"),
        rs.getBoolean("deadline"),
        rs.getBoolean("correction"),
        rs.getBoolean("follow_up"),
        rs.getBoolean("quiet_enabled"));
  }
}
