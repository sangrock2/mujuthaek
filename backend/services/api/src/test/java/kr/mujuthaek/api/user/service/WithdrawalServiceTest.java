package kr.mujuthaek.api.user.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.common.event.UserWithdrawn;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.user.domain.SocialAccount;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.repository.RefreshTokenRepository;
import kr.mujuthaek.api.user.repository.SocialAccountRepository;
import kr.mujuthaek.api.user.repository.UserRepository;
import kr.mujuthaek.api.user.repository.WithdrawalTicketRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@Import(TestcontainersConfiguration.class)
@Transactional
@RecordApplicationEvents
class WithdrawalServiceTest {

  @Autowired WithdrawalService withdrawals;
  @Autowired SocialLoginService socialLoginService;
  @Autowired AuthTokenService tokens;
  @Autowired UserRepository users;
  @Autowired SocialAccountRepository socialAccounts;
  @Autowired RefreshTokenRepository refreshTokens;
  @Autowired WithdrawalTicketRepository tickets;
  @Autowired ApplicationEventPublisher publisher;
  @Autowired ApplicationEvents events;

  private LoginUser login(SocialProvider provider, String id) {
    return socialLoginService.login(new SocialProfile(provider, id, "닉" + id));
  }

  @Test
  void startIssuesOneTimeTicketForLinkedProvider() {
    LoginUser user = login(SocialProvider.NAVER, "w-1");

    WithdrawalStart first = withdrawals.start(user.userId(), null);
    WithdrawalStart second = withdrawals.start(user.userId(), "naver");

    assertThat(second.provider()).isEqualTo("NAVER");
    assertThat(second.ttl()).isEqualTo(Duration.ofMinutes(10));
    assertThat(tickets.findByTicketHash(AuthTokenService.hash(second.ticket()))).isPresent();
    assertThat(tickets.findByTicketHash(AuthTokenService.hash(first.ticket())))
        .isEmpty(); // 새로 시작하면 이전 티켓은 지워요
    assertThat(tickets.findByTicketHash(second.ticket())).isEmpty(); // 원문은 저장하지 않아요
  }

  @Test
  void startTellsOtherLinkedProviders() {
    LoginUser user = login(SocialProvider.KAKAO, "w-7");
    socialAccounts.save(
        new SocialAccount(user.userId(), SocialProvider.NAVER, "w-7-naver", Instant.now()));

    WithdrawalStart start = withdrawals.start(user.userId(), "kakao");

    assertThat(start.provider()).isEqualTo("KAKAO");
    assertThat(start.otherProviders()).containsExactly("NAVER"); // 서버가 못 끊는 연결
  }

  @Test
  void deleteExpiredTicketsKeepsLiveOnes() {
    LoginUser old = login(SocialProvider.KAKAO, "w-8");
    LoginUser live = login(SocialProvider.KAKAO, "w-9");
    Clock past = Clock.fixed(Instant.now().minus(Duration.ofMinutes(11)), ZoneOffset.UTC);
    String oldTicket =
        new WithdrawalService(users, socialAccounts, tickets, publisher, past)
            .start(old.userId(), null)
            .ticket();
    String liveTicket = withdrawals.start(live.userId(), null).ticket();

    assertThat(withdrawals.deleteExpiredTickets()).isPositive();
    assertThat(tickets.findByTicketHash(AuthTokenService.hash(oldTicket))).isEmpty();
    assertThat(tickets.findByTicketHash(AuthTokenService.hash(liveTicket))).isPresent();
  }

  @Test
  void startWithNotLinkedProviderFails() {
    LoginUser user = login(SocialProvider.KAKAO, "w-2");

    assertThatThrownBy(() -> withdrawals.start(user.userId(), "google"))
        .isInstanceOf(CustomException.class)
        .extracting(e -> ((CustomException) e).errorCode())
        .isEqualTo(ErrorCode.WITHDRAWAL_PROVIDER_NOT_LINKED);
  }

  @Test
  void ticketIsOneTimeAndBoundToProvider() {
    LoginUser user = login(SocialProvider.GOOGLE, "w-3");
    String ticket = withdrawals.start(user.userId(), null).ticket();

    assertThatThrownBy(() -> withdrawals.consume(ticket, SocialProvider.KAKAO))
        .isInstanceOf(CustomException.class); // 다른 소셜로 로그인
    assertThatThrownBy(() -> withdrawals.consume(ticket, SocialProvider.GOOGLE))
        .isInstanceOf(CustomException.class); // 이미 지워짐

    String again = withdrawals.start(user.userId(), null).ticket();
    assertThat(withdrawals.consume(again, SocialProvider.GOOGLE)).isEqualTo(user.userId());
    assertThatThrownBy(() -> withdrawals.consume(again, SocialProvider.GOOGLE))
        .isInstanceOf(CustomException.class); // 일회용
  }

  @Test
  void expiredTicketIsRejected() {
    LoginUser user = login(SocialProvider.KAKAO, "w-4");
    Clock past = Clock.fixed(Instant.now().minus(Duration.ofMinutes(11)), ZoneOffset.UTC);
    var oldService = new WithdrawalService(users, socialAccounts, tickets, publisher, past);
    String ticket = oldService.start(user.userId(), null).ticket();

    assertThatThrownBy(() -> withdrawals.consume(ticket, SocialProvider.KAKAO))
        .isInstanceOf(CustomException.class)
        .extracting(e -> ((CustomException) e).errorCode())
        .isEqualTo(ErrorCode.WITHDRAWAL_TICKET_INVALID);
  }

  @Test
  void withdrawDeletesEverythingAndPublishesEvent() {
    LoginUser user = login(SocialProvider.KAKAO, "w-5");
    String phone = tokens.issue(user).refreshToken();
    String laptop = tokens.issue(user).refreshToken();

    withdrawals.withdraw(user.userId(), SocialProvider.KAKAO, "w-5");

    assertThat(users.findById(user.userId())).isEmpty();
    assertThat(socialAccounts.findByUserIdOrderByCreatedAt(user.userId())).isEmpty(); // cascade
    assertThat(refreshTokens.findByTokenHash(AuthTokenService.hash(phone)))
        .isEmpty(); // 모든 기기 로그아웃 (cascade)
    assertThat(refreshTokens.findByTokenHash(AuthTokenService.hash(laptop))).isEmpty();
    assertThat(events.stream(UserWithdrawn.class))
        .containsExactly(new UserWithdrawn(user.userId()));
  }

  @Test
  void withdrawWithOtherSocialAccountIsRejected() {
    LoginUser user = login(SocialProvider.NAVER, "w-6");
    login(SocialProvider.NAVER, "someone-else");

    assertThatThrownBy(
            () -> withdrawals.withdraw(user.userId(), SocialProvider.NAVER, "someone-else"))
        .isInstanceOf(CustomException.class)
        .extracting(e -> ((CustomException) e).errorCode())
        .isEqualTo(ErrorCode.WITHDRAWAL_ACCOUNT_MISMATCH);
    assertThat(users.findById(user.userId())).isPresent();
    assertThat(events.stream(UserWithdrawn.class)).isEmpty();
  }
}
