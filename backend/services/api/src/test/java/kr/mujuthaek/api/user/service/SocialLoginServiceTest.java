package kr.mujuthaek.api.user.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import jakarta.persistence.EntityManager;
import java.util.UUID;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.repository.SocialAccountRepository;
import kr.mujuthaek.api.user.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@Import(TestcontainersConfiguration.class)
@Transactional
class SocialLoginServiceTest {

  @Autowired SocialLoginService socialLoginService;
  @Autowired UserService userService;
  @Autowired UserRepository users;
  @Autowired SocialAccountRepository socialAccounts;
  @Autowired JdbcTemplate jdbc;
  @Autowired EntityManager entityManager;

  @Test
  void firstLoginJoinsAsUser() {
    LoginUser user =
        socialLoginService.login(new SocialProfile(SocialProvider.KAKAO, "111", "무주택러"));

    assertThat(user.role()).isEqualTo("USER");
    assertThat(user.isAdmin()).isFalse();
    assertThat(user.nickname()).isEqualTo("무주택러");
    assertThat(socialAccounts.findByProviderAndProviderUserId(SocialProvider.KAKAO, "111"))
        .get()
        .extracting(a -> a.getUserId())
        .isEqualTo(user.userId());
    assertThat(users.findById(user.userId()).orElseThrow().getLastLoginAt()).isNotNull();
  }

  @Test
  void joinedOnlyOnFirstLogin() {
    var first = socialLoginService.loginOrJoin(new SocialProfile(SocialProvider.NAVER, "j1", "처음"));
    var again = socialLoginService.loginOrJoin(new SocialProfile(SocialProvider.NAVER, "j1", "처음"));

    assertThat(first.joined()).isTrue();
    assertThat(again.joined()).isFalse();
    assertThat(again.user().userId()).isEqualTo(first.user().userId());
  }

  @Test
  void secondLoginKeepsSameUserAndUpdatesNickname() {
    LoginUser first =
        socialLoginService.login(new SocialProfile(SocialProvider.KAKAO, "222", "처음"));
    LoginUser again =
        socialLoginService.login(new SocialProfile(SocialProvider.KAKAO, "222", "바뀐닉"));
    LoginUser noNickname =
        socialLoginService.login(new SocialProfile(SocialProvider.KAKAO, "222", null));

    assertThat(again.userId()).isEqualTo(first.userId());
    assertThat(again.nickname()).isEqualTo("바뀐닉");
    assertThat(noNickname.nickname()).isEqualTo("바뀐닉"); // 동의를 끊어도 이전 닉네임은 남겨요
    assertThat(socialAccounts.findByUserIdOrderByCreatedAt(first.userId())).hasSize(1);
  }

  @Test
  void adminRoleIsKeptOnLogin() {
    LoginUser first =
        socialLoginService.login(new SocialProfile(SocialProvider.KAKAO, "333", "관리자"));
    users.flush();
    jdbc.update("update account.users set role = 'ADMIN' where id = ?", first.userId());
    entityManager.clear(); // 같은 트랜잭션의 JPA 캐시를 비워 DB 값을 다시 읽어요

    LoginUser again =
        socialLoginService.login(new SocialProfile(SocialProvider.KAKAO, "333", "관리자"));

    assertThat(again.role()).isEqualTo("ADMIN");
    assertThat(again.isAdmin()).isTrue();
    assertThat(again.getAuthorities()).extracting(Object::toString).containsExactly("ROLE_ADMIN");
  }

  @Test
  void longNicknameIsCut() {
    LoginUser user =
        socialLoginService.login(new SocialProfile(SocialProvider.KAKAO, "444", "가".repeat(80)));
    assertThat(user.nickname()).hasSize(50);
  }

  @Test
  void me() {
    LoginUser user = socialLoginService.login(new SocialProfile(SocialProvider.KAKAO, "555", "나"));

    var me = userService.getMe(user.userId());

    assertThat(me.id()).isEqualTo(user.userId());
    assertThat(me.nickname()).isEqualTo("나");
    assertThat(me.role()).isEqualTo("USER");
    assertThat(me.providers()).containsExactly("KAKAO");
    assertThat(me.joinedAt()).isNotNull();
  }

  @Test
  void meForUnknownUser() {
    assertThatThrownBy(() -> userService.getMe(UUID.randomUUID()))
        .isInstanceOf(CustomException.class)
        .extracting(e -> ((CustomException) e).errorCode())
        .isEqualTo(ErrorCode.UNAUTHENTICATED);
  }
}
