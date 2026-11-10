package kr.mujuthaek.api.user.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import jakarta.persistence.EntityManager;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.repository.RefreshTokenRepository;
import kr.mujuthaek.api.user.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@Import(TestcontainersConfiguration.class)
@Transactional
class AuthTokenServiceTest {

  @Autowired AuthTokenService tokens;
  @Autowired SocialLoginService socialLoginService;
  @Autowired JwtEncoder jwtEncoder;
  @Autowired JwtDecoder jwtDecoder;
  @Autowired JwtProperties props;
  @Autowired RefreshTokenRepository refreshTokens;
  @Autowired UserRepository users;
  @Autowired kr.mujuthaek.api.user.repository.AdminUserRepository admins;
  @Autowired JdbcTemplate jdbc;
  @Autowired EntityManager entityManager;

  private LoginUser login(String kakaoId) {
    return socialLoginService.login(
        new SocialProfile(SocialProvider.KAKAO, kakaoId, "닉" + kakaoId));
  }

  @Test
  void accessTokenCarriesUserIdRoleNickname() {
    LoginUser user = login("3001");

    var jwt = jwtDecoder.decode(tokens.issue(user).accessToken());

    assertThat(jwt.getSubject()).isEqualTo(user.userId().toString());
    assertThat(jwt.getClaimAsString(AuthTokenService.ROLE_CLAIM)).isEqualTo("USER");
    assertThat(jwt.getClaimAsString(AuthTokenService.NICKNAME_CLAIM)).isEqualTo("닉3001");
    assertThat(jwt.getClaimAsString("iss")).isEqualTo("mujuthaek-api");
    assertThat(Duration.between(jwt.getIssuedAt(), jwt.getExpiresAt()))
        .isEqualTo(Duration.ofMinutes(30));
  }

  @Test
  void concurrentRefreshLoserAlsoGetsTokens() {
    // 두 요청이 같은 쿠키로 동시에 찾기를 통과하고, 먼저 온 쪽이 바꾼 시각을 적어 늦은 쪽의 표시가 0줄인 경우.
    // 예전에는 409로 끝나 프론트가 로그아웃으로 봤어요. 지금은 늦은 쪽도 새 토큰을 받아요(2026-10-29)
    LoginUser user = login("3010");
    users.flush();
    var repo = org.mockito.Mockito.mock(RefreshTokenRepository.class);
    var saved =
        new kr.mujuthaek.api.user.domain.RefreshToken(
            user.userId(),
            AuthTokenService.hash("raw"),
            Instant.now().plus(Duration.ofDays(1)),
            Instant.now());
    org.mockito.Mockito.when(repo.findByTokenHash(AuthTokenService.hash("raw")))
        .thenReturn(java.util.Optional.of(saved));
    org.mockito.Mockito.when(
            repo.markRotated(
                org.mockito.ArgumentMatchers.eq(AuthTokenService.hash("raw")),
                org.mockito.ArgumentMatchers.any()))
        .thenReturn(0);
    var service = new AuthTokenService(jwtEncoder, props, repo, users, admins, Clock.systemUTC());

    var pair = service.refresh("raw");

    assertThat(pair.accessToken()).isNotBlank();
    assertThat(pair.refreshToken()).isNotEqualTo("raw");
  }

  @Test
  void rotatedRefreshTokenIsAcceptedOnlyWithinGrace() {
    // 새로고침 연타·탭 여러 개: 바꾼 옛 쿠키가 잠깐 뒤에 또 와도 로그아웃되지 않아요. 30초가 지나면 받지 않아요
    LoginUser user = login("3011");
    Instant t0 = Instant.now();
    String raw = at(t0).issue(user).refreshToken();

    String first = at(t0).refresh(raw).refreshToken();
    var late = at(t0.plusSeconds(10)).refresh(raw);

    assertThat(late.refreshToken()).isNotEqualTo(first).isNotEqualTo(raw);
    assertThat(at(t0.plusSeconds(10)).refresh(first).accessToken())
        .isNotBlank(); // 먼저 받은 새 값도 그대로 써요
    assertThatThrownBy(
            () -> at(t0.plus(AuthTokenService.ROTATED_GRACE).plusSeconds(1)).refresh(raw))
        .isInstanceOf(CustomException.class)
        .extracting(e -> ((CustomException) e).errorCode())
        .isEqualTo(ErrorCode.INVALID_REFRESH_TOKEN);
  }

  @Test
  void cleanupDeletesRotatedTokensPastGraceButKeepsFreshOnes() {
    LoginUser user = login("3012");
    Instant t0 = Instant.now();
    String raw = at(t0).issue(user).refreshToken();
    String fresh = at(t0).refresh(raw).refreshToken();

    at(t0.plus(AuthTokenService.ROTATED_GRACE).plusSeconds(1)).deleteExpired();

    assertThat(refreshTokens.findByTokenHash(AuthTokenService.hash(raw))).isEmpty();
    assertThat(refreshTokens.findByTokenHash(AuthTokenService.hash(fresh))).isPresent();
  }

  private AuthTokenService at(Instant now) {
    return new AuthTokenService(
        jwtEncoder, props, refreshTokens, users, admins, Clock.fixed(now, ZoneOffset.UTC));
  }

  @Test
  void refreshAndWithdrawalTicketsUseUrlSafeRandomTokens() {
    String a = AuthTokenService.randomToken();
    String b = AuthTokenService.randomToken();

    assertThat(a).hasSize(43).matches("[A-Za-z0-9_-]+").isNotEqualTo(b); // 32바이트 Base64url
  }

  @Test
  void refreshTokenIsStoredOnlyAsHash() {
    String raw = tokens.issue(login("3002")).refreshToken();

    assertThat(refreshTokens.findByTokenHash(raw)).isEmpty();
    assertThat(refreshTokens.findByTokenHash(AuthTokenService.hash(raw))).isPresent();
  }

  @Test
  void refreshUsesCurrentRole() {
    LoginUser user = login("3003");
    String raw = tokens.issue(user).refreshToken();
    users.flush();
    jdbc.update("update account.users set role = 'ADMIN' where id = ?", user.userId());
    entityManager.clear();

    var pair = tokens.refresh(raw);

    assertThat(jwtDecoder.decode(pair.accessToken()).getClaimAsString(AuthTokenService.ROLE_CLAIM))
        .isEqualTo("ADMIN");
    assertThat(pair.refreshToken()).isNotEqualTo(raw); // 회전: 새 값으로 바꿔요
  }

  @Test
  void expiredRefreshTokenIsRejectedAndDeleted() {
    LoginUser user = login("3004");
    Clock past = Clock.fixed(Instant.now().minus(Duration.ofDays(15)), ZoneOffset.UTC);
    var oldService = new AuthTokenService(jwtEncoder, props, refreshTokens, users, admins, past);
    String raw = oldService.issue(user).refreshToken();

    assertThatThrownBy(() -> tokens.refresh(raw))
        .isInstanceOf(CustomException.class)
        .extracting(e -> ((CustomException) e).errorCode())
        .isEqualTo(ErrorCode.INVALID_REFRESH_TOKEN);
    assertThat(refreshTokens.findByTokenHash(AuthTokenService.hash(raw))).isEmpty();
  }

  @Test
  void unknownRefreshToken() {
    assertThatThrownBy(() -> tokens.refresh("nope")).isInstanceOf(CustomException.class);
  }

  @Test
  void refreshForDeletedUserIsRejected() {
    LoginUser user = login("3005");
    String raw = tokens.issue(user).refreshToken();
    var other = login("3006");
    users.flush();
    jdbc.update(
        "update account.refresh_tokens set user_id = ? where token_hash = ?",
        other.userId(),
        AuthTokenService.hash(raw));
    jdbc.update(
        "delete from account.users where id = ?",
        other.userId()); // 탈퇴하면 refresh token도 같이 지워져요 (cascade)
    entityManager.clear();

    assertThatThrownBy(() -> tokens.refresh(raw)).isInstanceOf(CustomException.class);
  }

  @Test
  void revokeAndRevokeAll() {
    LoginUser user = login("3007");
    String a = tokens.issue(user).refreshToken();
    String b = tokens.issue(user).refreshToken();
    String c = tokens.issue(user).refreshToken();

    tokens.revoke(a);
    assertThat(refreshTokens.findByTokenHash(AuthTokenService.hash(a))).isEmpty();
    assertThat(refreshTokens.findByTokenHash(AuthTokenService.hash(b))).isPresent();

    tokens.revokeAll(user.userId());
    assertThat(refreshTokens.findByTokenHash(AuthTokenService.hash(c))).isEmpty();
    tokens.revoke("already-gone"); // 없는 값이어도 오류 없이 넘어가요
  }

  @Test
  void deleteExpired() {
    LoginUser user = login("3008");
    Clock past = Clock.fixed(Instant.now().minus(Duration.ofDays(30)), ZoneOffset.UTC);
    new AuthTokenService(jwtEncoder, props, refreshTokens, users, admins, past).issue(user);
    String fresh = tokens.issue(user).refreshToken();

    assertThat(tokens.deleteExpired()).isGreaterThanOrEqualTo(1);
    assertThat(refreshTokens.findByTokenHash(AuthTokenService.hash(fresh))).isPresent();
  }

  @Test
  void shortSecretIsRejected() {
    assertThatThrownBy(
            () ->
                new JwtProperties("short", "iss", Duration.ofMinutes(1), Duration.ofDays(1), false))
        .isInstanceOf(IllegalStateException.class);
    assertThatThrownBy(
            () -> new JwtProperties(null, "iss", Duration.ofMinutes(1), Duration.ofDays(1), false))
        .isInstanceOf(IllegalStateException.class);
  }
}
