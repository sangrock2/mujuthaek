package kr.mujuthaek.api.user.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.user.repository.NotificationEmailRepository;
import kr.mujuthaek.api.user.repository.NotificationEmailRepository.Saved;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.SimpleTransactionStatus;
import org.springframework.transaction.support.TransactionCallback;
import org.springframework.transaction.support.TransactionOperations;
import org.springframework.web.client.ResourceAccessException;

/**
 * 보안 감사 M-3: 인증 메일 호출이 시간 초과로 실패하면 트랜잭션이 되돌려지며 횟수 기록도 사라졌지만 알림 서버는 메일을 보냈어요. 시도는 메일을 보내기 전에 커밋하고,
 * 메일은 트랜잭션 밖에서 보내야 해요.
 */
class EmailVerificationRequestTest {

  private static final UUID USER = UUID.randomUUID();
  private static final Clock CLOCK =
      Clock.fixed(Instant.parse("2026-11-16T03:00:00Z"), ZoneOffset.UTC);

  /** 커밋된 행과, 트랜잭션 안에서만 보이는 쓰기. 콜백이 예외로 끝나면 되돌려요. */
  private final AtomicReference<Saved> committed = new AtomicReference<>();

  private final AtomicReference<Saved> pending = new AtomicReference<>();
  private final List<String> events = new ArrayList<>();

  private final TransactionOperations transactions =
      new TransactionOperations() {
        @Override
        public <T> T execute(TransactionCallback<T> action) {
          TransactionStatus status = new SimpleTransactionStatus(true);
          events.add("begin");
          try {
            T result = action.doInTransaction(status);
            if (pending.get() != null) committed.set(pending.get());
            events.add("commit");
            return result;
          } catch (RuntimeException e) {
            events.add("rollback");
            throw e;
          } finally {
            pending.set(null);
          }
        }
      };

  private NotificationEmailRepository repository() {
    var emails = mock(NotificationEmailRepository.class);
    when(emails.find(USER))
        .thenAnswer(
            i -> Optional.ofNullable(pending.get() != null ? pending.get() : committed.get()));
    doAnswer(
            i -> {
              Instant now = i.getArgument(4);
              pending.set(
                  new Saved(
                      USER,
                      i.getArgument(1),
                      i.getArgument(2),
                      now.plusSeconds(900),
                      now,
                      i.getArgument(5),
                      i.getArgument(6),
                      null,
                      false,
                      false,
                      false,
                      false,
                      i.getArgument(3),
                      null));
              return null;
            })
        .when(emails)
        .request(
            eq(USER),
            anyString(),
            anyString(),
            anyString(),
            any(Instant.class),
            any(LocalDate.class),
            anyInt(),
            anyBoolean());
    return emails;
  }

  @Test
  void aTimedOutMailStillCountsTheAttemptAndTheNextRequestIsRateLimited() {
    EmailVerificationSender timingOut =
        (address, token) -> {
          events.add("send");
          throw new ResourceAccessException("Read timed out");
        };
    var service =
        new EmailNotificationService(repository(), timingOut, CLOCK, transactions, "secret", "");

    assertThatThrownBy(() -> service.request(USER, "victim@example.com"))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.EMAIL_DELIVERY_UNAVAILABLE));
    assertThat(committed.get()).isNotNull();
    assertThat(committed.get().requestCount()).isEqualTo(1);

    // 예전에는 횟수가 되돌려져 곧바로 다시 보낼 수 있었어요
    assertThatThrownBy(() -> service.request(USER, "victim@example.com"))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.RATE_LIMITED));
    assertThat(events).containsExactly("begin", "commit", "send", "begin", "rollback");
  }

  @Test
  void theMailIsSentOnlyAfterTheAttemptIsCommitted() {
    EmailVerificationSender sender =
        (address, token) -> {
          assertThat(committed.get()).isNotNull();
          assertThat(committed.get().tokenHash()).isEqualTo(EmailNotificationService.hash(token));
          events.add("send");
        };
    var service =
        new EmailNotificationService(repository(), sender, CLOCK, transactions, "secret", "");

    service.request(USER, "me@example.com");

    assertThat(events).containsExactly("begin", "commit", "send");
  }
}
