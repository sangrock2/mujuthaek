package kr.mujuthaek.api.user.service;

import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import kr.mujuthaek.api.common.event.UserNicknameReplaced;
import kr.mujuthaek.api.user.domain.SocialAccount;
import kr.mujuthaek.api.user.domain.User;
import kr.mujuthaek.api.user.repository.SocialAccountRepository;
import kr.mujuthaek.api.user.repository.UserRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 소셜 로그인 처리: 처음이면 가입(USER), 이미 있으면 닉네임·마지막 로그인 시각만 갱신해요.
 *
 * <p>닉네임을 주지 않는 제공자(구글: 실명만 줘요)로 가입하면 「회원1234」 같은 별칭을 만들어요. 예전에 구글 실명을 닉네임으로 저장한 회원은 다음 로그인 때 별칭으로
 * 바꾸고, 채팅에 남은 지난 글의 작성자 이름도 바꾸게 알려요(2026-11-16 보안 감사 L-8).
 */
@Service
public class SocialLoginService {

  private static final SecureRandom RANDOM = new SecureRandom();

  private final UserRepository users;
  private final SocialAccountRepository socialAccounts;
  private final Clock clock;
  private final ApplicationEventPublisher events;

  @Autowired
  public SocialLoginService(
      UserRepository users,
      SocialAccountRepository socialAccounts,
      ApplicationEventPublisher events) {
    this(users, socialAccounts, Clock.systemUTC(), events);
  }

  SocialLoginService(
      UserRepository users,
      SocialAccountRepository socialAccounts,
      Clock clock,
      ApplicationEventPublisher events) {
    this.users = users;
    this.socialAccounts = socialAccounts;
    this.clock = clock;
    this.events = events;
  }

  /** 별칭: 「회원」 + 네 자리 숫자. 겹쳐도 괜찮아요 (닉네임은 유일하지 않아요) */
  static String alias() {
    return "회원" + (1000 + RANDOM.nextInt(9000));
  }

  /** 로그인 결과. joined = 이번에 처음 가입했는지 (프론트가 약관 동의 화면으로 보낼지 정해요) */
  public record SocialLogin(LoginUser user, boolean joined) {}

  @Transactional
  public LoginUser login(SocialProfile profile) {
    return loginOrJoin(profile).user();
  }

  @Transactional
  public SocialLogin loginOrJoin(SocialProfile profile) {
    Instant now = clock.instant();
    var existing =
        socialAccounts
            .findByProviderAndProviderUserId(profile.provider(), profile.providerUserId())
            .flatMap(account -> users.findById(account.getUserId()));
    existing.ifPresent(
        user -> {
          user.loggedIn(profile.nickname(), now);
          replaceRealName(user, profile, now);
        });
    User user = existing.orElseGet(() -> join(profile, now));
    return new SocialLogin(
        new LoginUser(user.getId(), user.getNickname(), user.getRole().name()), existing.isEmpty());
  }

  /**
   * 제공자가 닉네임을 주지 않았는데, 지금 닉네임이 비었거나 제공자가 준 실명과 같으면 별칭으로 바꿔요 (실명 자체는 저장하지 않아요). 제공자가 닉네임을 주면 그대로
   * 따라가요(loggedIn).
   */
  private void replaceRealName(User user, SocialProfile profile, Instant now) {
    if (profile.nickname() != null) {
      return;
    }
    String current = user.getNickname();
    boolean replace =
        current == null
            || profile.realNames().stream().map(User::normalizedNickname).anyMatch(current::equals);
    if (replace) {
      String alias = alias();
      user.rename(alias, now);
      events.publishEvent(new UserNicknameReplaced(user.getId(), alias));
    }
  }

  private User join(SocialProfile profile, Instant now) {
    String nickname = profile.nickname() != null ? profile.nickname() : alias();
    User user = users.save(User.join(nickname, now));
    socialAccounts.save(
        new SocialAccount(user.getId(), profile.provider(), profile.providerUserId(), now));
    return user;
  }
}
