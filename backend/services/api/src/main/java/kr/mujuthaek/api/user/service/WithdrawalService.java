package kr.mujuthaek.api.user.service;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.common.event.UserWithdrawn;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.user.domain.SocialAccount;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.domain.WithdrawalTicket;
import kr.mujuthaek.api.user.repository.SocialAccountRepository;
import kr.mujuthaek.api.user.repository.UserRepository;
import kr.mujuthaek.api.user.repository.WithdrawalTicketRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 탈퇴 (hard delete). 흐름: {@link #start} 티켓 발급 → 소셜 다시 로그인(재인증) → {@link #consume} 티켓 확인 → {@link
 * #withdraw} 계정 일치 확인·회원 삭제·이벤트 → (커밋 뒤) 소셜 연결 끊기는 security 쪽에서 해요.
 */
@Service
public class WithdrawalService {

  static final Duration TICKET_TTL = Duration.ofMinutes(10);

  private final UserRepository users;
  private final SocialAccountRepository socialAccounts;
  private final WithdrawalTicketRepository tickets;
  private final ApplicationEventPublisher events;
  private final Clock clock;

  @Autowired
  public WithdrawalService(
      UserRepository users,
      SocialAccountRepository socialAccounts,
      WithdrawalTicketRepository tickets,
      ApplicationEventPublisher events) {
    this(users, socialAccounts, tickets, events, Clock.systemUTC());
  }

  WithdrawalService(
      UserRepository users,
      SocialAccountRepository socialAccounts,
      WithdrawalTicketRepository tickets,
      ApplicationEventPublisher events,
      Clock clock) {
    this.users = users;
    this.socialAccounts = socialAccounts;
    this.tickets = tickets;
    this.events = events;
    this.clock = clock;
  }

  /** 탈퇴 시작: 다시 로그인할 소셜을 정하고 일회용 티켓을 만들어요 (이전 티켓은 지워요). provider를 비우면 처음 연결한 소셜이에요. */
  @Transactional
  public WithdrawalStart start(UUID userId, String provider) {
    var linked = socialAccounts.findByUserIdOrderByCreatedAt(userId);
    SocialAccount account =
        linked.stream()
            .filter(
                a ->
                    provider == null
                        || provider.isBlank()
                        || a.getProvider().name().equalsIgnoreCase(provider))
            .findFirst()
            .orElseThrow(() -> new CustomException(ErrorCode.WITHDRAWAL_PROVIDER_NOT_LINKED));
    tickets.deleteByUserId(userId);
    Instant now = clock.instant();
    String raw = AuthTokenService.randomToken();
    tickets.save(
        new WithdrawalTicket(
            userId, account.getProvider(), AuthTokenService.hash(raw), now.plus(TICKET_TTL), now));
    // 제공자 토큰을 저장하지 않아서, 다시 로그인한 소셜만 연결을 끊을 수 있어요. 나머지는 화면에서 각 서비스에서 직접 해제하라고 알려요
    List<String> others =
        linked.stream()
            .map(a -> a.getProvider().name())
            .filter(name -> !name.equals(account.getProvider().name()))
            .toList();
    return new WithdrawalStart(account.getProvider().name(), raw, TICKET_TTL, others);
  }

  /** 만료된 탈퇴 티켓 정리 (탈퇴를 시작하고 재인증을 끝내지 않은 것). */
  @Transactional
  public int deleteExpiredTickets() {
    return tickets.deleteExpired(clock.instant());
  }

  /** 재인증 콜백: 티켓을 확인하고 지워요 (일회용). 없거나 만료됐거나 다른 소셜로 로그인했으면 실패. 탈퇴할 회원 ID를 돌려줘요. */
  @Transactional(noRollbackFor = CustomException.class) // 실패해도 티켓은 지운 채로
  public UUID consume(String rawTicket, SocialProvider provider) {
    String hash = AuthTokenService.hash(rawTicket);
    WithdrawalTicket ticket =
        tickets
            .findByTicketHash(hash)
            .orElseThrow(() -> new CustomException(ErrorCode.WITHDRAWAL_TICKET_INVALID));
    if (tickets.deleteByTicketHash(hash) == 0
        || ticket.expired(clock.instant())
        || ticket.getProvider() != provider) {
      throw new CustomException(ErrorCode.WITHDRAWAL_TICKET_INVALID); // 동시에 쓰였거나, 만료, 다른 소셜
    }
    return ticket.getUserId();
  }

  /**
   * 회원 삭제 (hard delete). 다시 로그인한 소셜 계정이 이 회원에 연결된 계정인지 먼저 확인해요 (다른 계정으로 로그인하면 엉뚱한 회원이나 남의 연결을 지우지
   * 않게). 소셜 계정·refresh token은 cascade로 지워지고, 다른 모듈은 {@link UserWithdrawn} 이벤트로 자기 데이터를 지워요.
   */
  @Transactional
  public void withdraw(UUID userId, SocialProvider provider, String providerUserId) {
    socialAccounts
        .findByProviderAndProviderUserId(provider, providerUserId)
        .filter(account -> account.getUserId().equals(userId))
        .orElseThrow(() -> new CustomException(ErrorCode.WITHDRAWAL_ACCOUNT_MISMATCH));
    users.deleteUser(userId);
    events.publishEvent(new UserWithdrawn(userId));
  }
}
