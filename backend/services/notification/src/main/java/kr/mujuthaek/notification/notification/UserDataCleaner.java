package kr.mujuthaek.notification.notification;

import java.time.Clock;
import java.time.ZoneOffset;
import java.util.Collection;
import java.util.Set;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * user.withdrawn: 탈퇴한 회원의 발송 줄(안 보낸 것 포함)을 모두 지우고, 탈퇴했다고 기록해요 (withdrawn_users). 탈퇴 전에 만든 알림 요청이 늦게
 * 와도 그 회원은 {@link #withdrawn}으로 걸러요.
 */
@Component
public class UserDataCleaner {

  private final JdbcClient jdbc;
  private final Clock clock;

  public UserDataCleaner(JdbcClient jdbc, Clock clock) {
    this.jdbc = jdbc;
    this.clock = clock;
  }

  @Transactional(propagation = Propagation.MANDATORY)
  public void delete(UUID userId) {
    jdbc.sql("delete from deliveries where user_id = :userId").param("userId", userId).update();
    jdbc.sql(
            """
            insert into withdrawn_users (user_id, withdrawn_at) values (:userId, :now)
            on conflict (user_id) do nothing
            """)
        .param("userId", userId)
        .param("now", clock.instant().atOffset(ZoneOffset.UTC))
        .update();
  }

  /** 이 중 탈퇴한 회원 */
  public Set<UUID> withdrawn(Collection<UUID> userIds) {
    if (userIds.isEmpty()) {
      return Set.of();
    }
    return Set.copyOf(
        jdbc.sql("select user_id from withdrawn_users where user_id in (:ids)")
            .param("ids", userIds)
            .query(UUID.class)
            .list());
  }
}
