package kr.mujuthaek.api.user.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import kr.mujuthaek.api.common.event.UserNicknameReplaced;
import kr.mujuthaek.api.user.domain.SocialAccount;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.domain.User;
import kr.mujuthaek.api.user.repository.SocialAccountRepository;
import kr.mujuthaek.api.user.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.context.ApplicationEventPublisher;

/** 구글 실명은 닉네임으로 쓰지 않고, 예전에 실명을 저장한 회원은 다음 로그인 때 별칭으로 바꿔요 (2026-11-16 보안 감사 L-8). */
class SocialLoginAliasTest {

  private static final Instant NOW = Instant.parse("2026-11-16T01:00:00Z");

  private final UserRepository users = mock(UserRepository.class);
  private final SocialAccountRepository accounts = mock(SocialAccountRepository.class);
  private final ApplicationEventPublisher events = mock(ApplicationEventPublisher.class);
  private final SocialLoginService service =
      new SocialLoginService(users, accounts, Clock.fixed(NOW, ZoneOffset.UTC), events);

  private User existing(SocialProvider provider, String id, String nickname) {
    User user = User.join(nickname, NOW.minusSeconds(86_400));
    UUID userId = UUID.randomUUID();
    when(accounts.findByProviderAndProviderUserId(provider, id))
        .thenReturn(Optional.of(new SocialAccount(userId, provider, id, NOW)));
    when(users.findById(userId)).thenReturn(Optional.of(user));
    return user;
  }

  @Test
  void newGoogleMemberGetsAnAliasInsteadOfTheRealName() {
    when(accounts.findByProviderAndProviderUserId(SocialProvider.GOOGLE, "g-1"))
        .thenReturn(Optional.empty());
    when(users.save(any(User.class))).thenAnswer(call -> call.getArgument(0));

    var login =
        service.loginOrJoin(
            new SocialProfile(SocialProvider.GOOGLE, "g-1", null, Set.of("홍길동", "길동")));

    assertThat(login.joined()).isTrue();
    assertThat(login.user().nickname()).matches("회원\\d{4}");
  }

  @Test
  void storedGoogleRealNameIsReplacedAndPastChatIsRenamed() {
    User user = existing(SocialProvider.GOOGLE, "g-2", "홍길동");

    service.loginOrJoin(
        new SocialProfile(SocialProvider.GOOGLE, "g-2", null, Set.of(" 홍길동 ", "길동")));

    assertThat(user.getNickname()).matches("회원\\d{4}");
    var event = ArgumentCaptor.forClass(UserNicknameReplaced.class);
    verify(events).publishEvent(event.capture());
    assertThat(event.getValue().nickname()).isEqualTo(user.getNickname());
  }

  @Test
  void aliasOrOtherNicknameIsKept() {
    User user = existing(SocialProvider.GOOGLE, "g-3", "회원1234");

    service.loginOrJoin(new SocialProfile(SocialProvider.GOOGLE, "g-3", null, Set.of("홍길동")));

    assertThat(user.getNickname()).isEqualTo("회원1234");
    verify(events, never()).publishEvent(any(Object.class));
  }

  @Test
  void kakaoNicknameStillFollowsTheProvider() {
    User user = existing(SocialProvider.KAKAO, "k-1", "예전닉");

    service.loginOrJoin(new SocialProfile(SocialProvider.KAKAO, "k-1", "새닉"));

    assertThat(user.getNickname()).isEqualTo("새닉");
    verify(events, never()).publishEvent(any(Object.class));
  }
}
