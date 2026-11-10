package kr.mujuthaek.api.user.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicBoolean;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.chat.event.ChatEvent;
import kr.mujuthaek.api.common.event.UserWithdrawn;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.repository.UserRepository;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * 탈퇴를 실제로 커밋해요(다른 탈퇴 시험은 트랜잭션을 되돌려 커밋 직전 정리가 돌지 않아요). 2026-11-10 재검토에서 빠졌다고 한 두 가지: 다른 모듈의 지우기가
 * 실패하면 탈퇴도 되돌려지는지, 커밋 직전에 지운 채팅 메시지의 실시간 이벤트가 커밋 뒤 나가는지.
 */
@SpringBootTest
@Import({TestcontainersConfiguration.class, WithdrawalCommitTest.Probe.class})
class WithdrawalCommitTest {

  @TestConfiguration
  static class Probe {
    static final AtomicBoolean FAIL = new AtomicBoolean();
    static final List<ChatEvent> SENT = new CopyOnWriteArrayList<>();

    @Bean
    Listener withdrawalProbe() {
      return new Listener();
    }

    static class Listener {
      /** 다른 모듈의 탈퇴 정리처럼 커밋 직전에 돌아요. FAIL이면 실패해요. */
      @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
      void cleanup(UserWithdrawn event) {
        if (FAIL.get()) {
          throw new IllegalStateException("지우기 실패");
        }
      }

      /** 채팅 SSE 중계처럼 커밋 뒤에 받아요. */
      @TransactionalEventListener
      void sent(ChatEvent event) {
        SENT.add(event);
      }
    }
  }

  @Autowired WithdrawalService withdrawals;
  @Autowired SocialLoginService logins;
  @Autowired UserRepository users;
  @Autowired JdbcTemplate jdbc;

  @AfterEach
  void reset() {
    Probe.FAIL.set(false);
    Probe.SENT.clear();
  }

  @Test
  void aFailedCleanupInAnotherModuleRollsTheWithdrawalBack() {
    LoginUser user = logins.login(new SocialProfile(SocialProvider.KAKAO, "wc-1", "닉wc-1"));
    UUID message = message(user);
    Probe.FAIL.set(true);

    assertThatThrownBy(() -> withdrawals.withdraw(user.userId(), SocialProvider.KAKAO, "wc-1"))
        .hasMessage("지우기 실패");

    assertThat(users.findById(user.userId())).isPresent();
    assertThat(
            jdbc.queryForObject(
                "select count(*) from chat.messages where id = ?", Long.class, message))
        .isEqualTo(1); // 채팅 지우기도 함께 되돌려짐
    assertThat(Probe.SENT).isEmpty(); // 되돌린 지우기는 화면에 보내지 않음
  }

  @Test
  void chatMessagesDeletedJustBeforeCommitAreBroadcastAfterIt() {
    LoginUser user = logins.login(new SocialProfile(SocialProvider.KAKAO, "wc-2", "닉wc-2"));
    UUID message = message(user);

    withdrawals.withdraw(user.userId(), SocialProvider.KAKAO, "wc-2");

    assertThat(users.findById(user.userId())).isEmpty();
    assertThat(
            jdbc.queryForObject(
                "select count(*) from chat.messages where id = ?", Long.class, message))
        .isZero();
    assertThat(Probe.SENT)
        .anySatisfy(
            event -> {
              assertThat(event.name()).isEqualTo("message.deleted");
              assertThat(event.data()).isEqualTo(new ChatEvent.MessageRef(message));
            });
  }

  private UUID message(LoginUser user) {
    UUID id = UUID.randomUUID();
    jdbc.update(
        """
        insert into chat.messages (id, notice_id, user_id, author_nickname, content, status, created_at)
        values (?, ?, ?, ?, '탈퇴 전 글', 'VISIBLE', ?)
        """,
        id,
        UUID.randomUUID(),
        user.userId(),
        user.nickname(),
        OffsetDateTime.now());
    return id;
  }
}
