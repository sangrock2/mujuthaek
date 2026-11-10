package kr.mujuthaek.api.user.service;

import java.time.Clock;
import java.time.Instant;
import kr.mujuthaek.api.user.domain.SocialAccount;
import kr.mujuthaek.api.user.domain.User;
import kr.mujuthaek.api.user.repository.SocialAccountRepository;
import kr.mujuthaek.api.user.repository.UserRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 소셜 로그인 처리: 처음이면 가입(USER), 이미 있으면 닉네임·마지막 로그인 시각만 갱신해요. */
@Service
public class SocialLoginService {

  private final UserRepository users;
  private final SocialAccountRepository socialAccounts;
  private final Clock clock;

  @Autowired
  public SocialLoginService(UserRepository users, SocialAccountRepository socialAccounts) {
    this(users, socialAccounts, Clock.systemUTC());
  }

  SocialLoginService(UserRepository users, SocialAccountRepository socialAccounts, Clock clock) {
    this.users = users;
    this.socialAccounts = socialAccounts;
    this.clock = clock;
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
    existing.ifPresent(user -> user.loggedIn(profile.nickname(), now));
    User user = existing.orElseGet(() -> join(profile, now));
    return new SocialLogin(
        new LoginUser(user.getId(), user.getNickname(), user.getRole().name()), existing.isEmpty());
  }

  private User join(SocialProfile profile, Instant now) {
    User user = users.save(User.join(profile.nickname(), now));
    socialAccounts.save(
        new SocialAccount(user.getId(), profile.provider(), profile.providerUserId(), now));
    return user;
  }
}
