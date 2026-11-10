package kr.mujuthaek.api.user.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import jakarta.servlet.http.Cookie;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.service.AuthTokenService;
import kr.mujuthaek.api.user.service.LoginUser;
import kr.mujuthaek.api.user.service.SocialLoginService;
import kr.mujuthaek.api.user.service.SocialProfile;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.user.DefaultOAuth2User;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

@SpringBootTest
@AutoConfigureMockMvc
@Import(TestcontainersConfiguration.class)
class SecurityIntegrationTest {

  @Autowired MockMvc mvc;
  @Autowired SocialLoginService socialLoginService;
  @Autowired SocialOAuth2UserService socialUserService;
  @Autowired AuthTokenService tokens;
  @Autowired LoginSuccessHandler loginSuccessHandler;
  @Autowired JwtEncoder jwtEncoder;
  @Autowired LoginFailureHandler loginFailureHandler;
  @Autowired RefreshTokenCookies refreshTokenCookies;
  @Autowired LoginProperties loginProperties;
  @Autowired kr.mujuthaek.api.user.service.WithdrawalService withdrawalService;
  @Autowired kr.mujuthaek.api.user.repository.UserRepository users;
  @Autowired org.springframework.jdbc.core.JdbcTemplate jdbc;

  private LoginUser login(String kakaoId) {
    return socialLoginService.login(
        new SocialProfile(SocialProvider.KAKAO, kakaoId, "회원" + kakaoId));
  }

  private String bearer(LoginUser user) {
    return "Bearer " + tokens.issue(user).accessToken();
  }

  private static Cookie refreshCookie(MvcResult result) {
    return result.getResponse().getCookie(RefreshTokenCookies.NAME);
  }

  @Test
  void meWithoutTokenIs401ProblemJson() throws Exception {
    mvc.perform(get("/api/users/me"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string("Content-Type", "application/problem+json;charset=UTF-8"))
        .andExpect(jsonPath("$.code").value("UNAUTHENTICATED"))
        .andExpect(jsonPath("$.status").value(401));
  }

  @Test
  void meWithAccessToken() throws Exception {
    LoginUser user = login("2001");
    mvc.perform(get("/api/users/me").header("Authorization", bearer(user)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(user.userId().toString()))
        .andExpect(jsonPath("$.nickname").value("회원2001"))
        .andExpect(jsonPath("$.role").value("USER"))
        .andExpect(jsonPath("$.providers[0]").value("KAKAO"));
  }

  @Test
  void brokenOrExpiredTokenIs401() throws Exception {
    LoginUser user = login("2002");
    var expired =
        JwtClaimsSet.builder()
            .issuer("mujuthaek-api")
            .subject(user.userId().toString())
            .issuedAt(Instant.now().minusSeconds(3600))
            .expiresAt(Instant.now().minusSeconds(60))
            .claim(AuthTokenService.ROLE_CLAIM, "USER")
            .build();
    String expiredToken =
        jwtEncoder
            .encode(JwtEncoderParameters.from(JwsHeader.with(MacAlgorithm.HS256).build(), expired))
            .getTokenValue();

    mvc.perform(get("/api/users/me").header("Authorization", "Bearer not-a-jwt"))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.code").value("UNAUTHENTICATED"));
    mvc.perform(get("/api/users/me").header("Authorization", "Bearer " + expiredToken))
        .andExpect(status().isUnauthorized());
  }

  @Test
  void adminPathsCheckPermissionsInDatabaseNotToken() throws Exception {
    LoginUser user = login("2003");
    // 토큰에 ADMIN이라고 적혀 있어도 DB에서 관리자가 아니면 막아요 (해제된 관리자의 남은 토큰)
    var claimsAdmin = new LoginUser(user.userId(), user.nickname(), "ADMIN");

    mvc.perform(get("/api/admin/reviews")).andExpect(status().isUnauthorized());
    mvc.perform(get("/api/admin/reviews").header("Authorization", bearer(user)))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("FORBIDDEN"));
    mvc.perform(get("/api/admin/reviews").header("Authorization", bearer(claimsAdmin)))
        .andExpect(status().isForbidden());

    // 관리자로 지정만 하면 내 상태만 볼 수 있어요
    jdbc.update("update account.users set role = 'ADMIN' where id = ?", user.userId());
    mvc.perform(get("/api/admin/me").header("Authorization", bearer(claimsAdmin)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.active").value(true))
        .andExpect(jsonPath("$.permissions").isEmpty());
    mvc.perform(get("/api/admin/reviews/counts").header("Authorization", bearer(claimsAdmin)))
        .andExpect(status().isForbidden());

    // 받은 권한의 경로만 열려요. 권한을 정하지 않은 관리자 경로는 최상위만
    jdbc.update(
        "insert into account.admin_permissions (user_id, permission) values (?, 'TRAFFIC')",
        user.userId());
    mvc.perform(get("/api/admin/traffic/anything").header("Authorization", bearer(claimsAdmin)))
        .andExpect(status().isNotFound());
    mvc.perform(get("/api/admin/reviews/counts").header("Authorization", bearer(claimsAdmin)))
        .andExpect(status().isForbidden());
    mvc.perform(get("/api/admin/anything").header("Authorization", bearer(claimsAdmin)))
        .andExpect(status().isForbidden());

    // 권한을 빼면 같은 토큰으로도 바로 막혀요
    jdbc.update("delete from account.admin_permissions where user_id = ?", user.userId());
    mvc.perform(get("/api/admin/traffic/anything").header("Authorization", bearer(claimsAdmin)))
        .andExpect(status().isForbidden());
    jdbc.update("update account.users set role = 'USER' where id = ?", user.userId());
  }

  @Test
  void reviewQueueNeedsTheReviewPermissionOfEveryKindAsked() throws Exception {
    LoginUser user = login("2099");
    var claimsAdmin = new LoginUser(user.userId(), user.nickname(), "ADMIN");
    jdbc.update("update account.users set role = 'ADMIN' where id = ?", user.userId());
    jdbc.update(
        "insert into account.admin_permissions (user_id, permission) values (?, 'BENEFIT_REVIEW')",
        user.userId());

    // 혜택 검수 권한만 있으면 혜택만 볼 수 있어요 (권한을 지나면 검수 API 연결 결과라 403만 아니면 돼요)
    mvc.perform(
            get("/api/admin/reviews/queue")
                .param("kinds", "BENEFIT")
                .header("Authorization", bearer(claimsAdmin)))
        .andExpect(result -> assertThat(result.getResponse().getStatus()).isNotEqualTo(403));
    mvc.perform(
            get("/api/admin/reviews/queue")
                .param("kinds", "NOTICE,BENEFIT")
                .header("Authorization", bearer(claimsAdmin)))
        .andExpect(status().isForbidden());
    mvc.perform(get("/api/admin/reviews/queue").header("Authorization", bearer(claimsAdmin)))
        .andExpect(status().isForbidden());
    mvc.perform(
            get("/api/admin/reviews/queue")
                .param("kinds", "ANY")
                .header("Authorization", bearer(claimsAdmin)))
        .andExpect(status().isForbidden());
    // 2026-11-10 코드 검토: kinds를 두 번 보내면 권한은 첫 값만 보고 컨트롤러는 둘 다 받아, 공고 검수 대기열까지 보였음
    mvc.perform(
            get("/api/admin/reviews/queue")
                .param("kinds", "BENEFIT", "NOTICE")
                .header("Authorization", bearer(claimsAdmin)))
        .andExpect(status().isForbidden());

    jdbc.update("delete from account.admin_permissions where user_id = ?", user.userId());
    jdbc.update("update account.users set role = 'USER' where id = ?", user.userId());
  }

  @Test
  void suspendedUserCannotLoginOrWrite() throws Exception {
    LoginUser user = login("2004");
    String token = bearer(user);
    jdbc.update(
        "insert into account.suspensions (user_id, reason) values (?, '시험')", user.userId());

    assertThatThrownBy(() -> tokens.issue(user))
        .isInstanceOf(kr.mujuthaek.api.common.exception.CustomException.class)
        .hasMessageContaining("이용이 정지된");
    mvc.perform(post("/api/users/me/anything").header("Authorization", token))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("ACCOUNT_SUSPENDED"));
    jdbc.update("delete from account.suspensions where user_id = ?", user.userId());
  }

  @Test
  void publicPathsNeedNoLogin() throws Exception {
    // 로그인 없이 열리는지만 봐요. 상태 코드는 DB·RabbitMQ 상태에 따라 200·503이 갈려서 비교하지 않아요
    mvc.perform(get("/actuator/health"))
        .andExpect(result -> assertThat(result.getResponse().getStatus()).isNotIn(401, 403));
  }

  @Test
  void loginStartsAtKakao() throws Exception {
    var result =
        mvc.perform(get("/oauth2/authorization/kakao"))
            .andExpect(status().is3xxRedirection())
            .andReturn();
    assertThat(result.getResponse().getRedirectedUrl())
        .startsWith("https://kauth.kakao.com/oauth/authorize")
        .contains("scope=profile_nickname")
        .contains("redirect_uri=http://localhost/login/oauth2/code/kakao");
  }

  @Test
  void loginStartsAtNaverAndGoogle() throws Exception {
    var naver =
        mvc.perform(get("/oauth2/authorization/naver"))
            .andExpect(status().is3xxRedirection())
            .andReturn();
    assertThat(naver.getResponse().getRedirectedUrl())
        .startsWith("https://nid.naver.com/oauth2.0/authorize")
        .contains("redirect_uri=http://localhost/login/oauth2/code/naver");

    var google =
        mvc.perform(get("/oauth2/authorization/google"))
            .andExpect(status().is3xxRedirection())
            .andReturn();
    assertThat(google.getResponse().getRedirectedUrl())
        .startsWith("https://accounts.google.com/o/oauth2/v2/auth")
        .contains("scope=profile")
        .doesNotContain("openid")
        .contains("redirect_uri=http://localhost/login/oauth2/code/google");
  }

  @Test
  void naverUserBecomesLoginUser() {
    var naver =
        new DefaultOAuth2User(
            List.of(),
            Map.of("resultcode", "00", "response", Map.of("id", "nv-1", "nickname", "네이버닉")),
            "response");

    var principal = (LoginUser) socialUserService.toLoginUser("naver", naver);

    assertThat(principal.nickname()).isEqualTo("네이버닉");
    assertThat(principal.role()).isEqualTo("USER");
  }

  @Test
  void loginSuccessSetsRefreshCookieAndGoesToFrontend() throws Exception {
    LoginUser user = login("2004");
    var request = new MockHttpServletRequest();
    request.getSession(true); // 카카오 로그인 중간에 쓴 세션
    var response = new MockHttpServletResponse();

    loginSuccessHandler.onAuthenticationSuccess(
        request, response, new TestingAuthenticationToken(user, null));

    assertThat(response.getRedirectedUrl()).isEqualTo("http://localhost:3000/auth/callback");
    assertThat(response.getHeader("Set-Cookie"))
        .startsWith(RefreshTokenCookies.NAME + "=")
        .contains("Path=/api/auth", "HttpOnly", "SameSite=Lax", "Max-Age=1209600");
    assertThat(request.getSession(false)).isNull(); // 로그인이 끝나면 세션을 지워요
  }

  @Test
  void refreshRotatesTokenAndOldOneStillWorksBriefly() throws Exception {
    LoginUser user = login("2005");
    var first = new Cookie(RefreshTokenCookies.NAME, tokens.issue(user).refreshToken());

    MvcResult refreshed =
        mvc.perform(post("/api/auth/refresh").cookie(first))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.tokenType").value("Bearer"))
            .andExpect(jsonPath("$.expiresIn").value(1800))
            .andReturn();
    String access =
        com.jayway.jsonpath.JsonPath.read(
            refreshed.getResponse().getContentAsString(), "$.accessToken");
    Cookie second = refreshCookie(refreshed);
    assertThat(second.getValue()).isNotEqualTo(first.getValue());

    mvc.perform(get("/api/users/me").header("Authorization", "Bearer " + access))
        .andExpect(status().isOk());
    // 바꾼 지 얼마 안 된 옛 값은 다시 와도 새 토큰을 받아요(새로고침 연타·탭 여러 개). 그 뒤로는 못 써요(AuthTokenServiceTest)
    MvcResult late =
        mvc.perform(post("/api/auth/refresh").cookie(first)).andExpect(status().isOk()).andReturn();
    assertThat(refreshCookie(late).getValue()).isNotEqualTo(first.getValue());
    mvc.perform(post("/api/auth/refresh").cookie(second)).andExpect(status().isOk());
  }

  @Test
  void refreshesWithTheSameCookieAtOnceAllSucceed() throws Exception {
    // 새로고침 연타·탭 여러 개: 같은 쿠키로 연장이 한꺼번에 와도 모두 새 토큰을 받아요(예전에는 늦은 쪽이 409·401로 로그아웃)
    LoginUser user = login("2098");
    var cookie = new Cookie(RefreshTokenCookies.NAME, tokens.issue(user).refreshToken());
    var start = new java.util.concurrent.CountDownLatch(1);
    var pool = java.util.concurrent.Executors.newFixedThreadPool(5);
    try {
      var results = new java.util.ArrayList<java.util.concurrent.Future<Integer>>();
      for (int i = 0; i < 5; i++) {
        results.add(
            pool.submit(
                () -> {
                  start.await();
                  return mvc.perform(post("/api/auth/refresh").cookie(cookie))
                      .andReturn()
                      .getResponse()
                      .getStatus();
                }));
      }
      start.countDown();
      for (var result : results) {
        assertThat(result.get()).isEqualTo(200);
      }
    } finally {
      pool.shutdownNow();
    }
  }

  @Test
  void refreshWithoutCookieIs401() throws Exception {
    mvc.perform(post("/api/auth/refresh"))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.code").value("INVALID_REFRESH_TOKEN"));
  }

  @Test
  void logoutRevokesRefreshToken() throws Exception {
    LoginUser user = login("2006");
    var cookie = new Cookie(RefreshTokenCookies.NAME, tokens.issue(user).refreshToken());

    MvcResult result =
        mvc.perform(post("/api/auth/logout").cookie(cookie))
            .andExpect(status().isNoContent())
            .andReturn();
    assertThat(refreshCookie(result).getMaxAge()).isZero();

    mvc.perform(post("/api/auth/refresh").cookie(cookie)).andExpect(status().isUnauthorized());
    mvc.perform(post("/api/auth/logout")).andExpect(status().isNoContent()); // 쿠키가 없어도 204
  }

  @Test
  void firstLoginGoesToCallbackWithNewFlag() throws Exception {
    var kakao =
        new DefaultOAuth2User(
            List.of(), Map.of("id", 778L, "properties", Map.of("nickname", "새회원")), "id");
    var callback = new MockHttpServletRequest();
    RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(callback));
    try {
      var first = (LoginUser) socialUserService.toLoginUser("kakao", kakao);
      var response = new MockHttpServletResponse();
      loginSuccessHandler.onAuthenticationSuccess(
          callback, response, new TestingAuthenticationToken(first, null));
      assertThat(response.getRedirectedUrl())
          .isEqualTo("http://localhost:3000/auth/callback?new=1");

      var again = new MockHttpServletRequest();
      RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(again));
      var second = (LoginUser) socialUserService.toLoginUser("kakao", kakao);
      var response2 = new MockHttpServletResponse();
      loginSuccessHandler.onAuthenticationSuccess(
          again, response2, new TestingAuthenticationToken(second, null));
      assertThat(response2.getRedirectedUrl()).isEqualTo("http://localhost:3000/auth/callback");
    } finally {
      RequestContextHolder.resetRequestAttributes();
    }
  }

  @Test
  void kakaoUserBecomesLoginUser() {
    var kakao =
        new DefaultOAuth2User(
            List.of(), Map.of("id", 777L, "properties", Map.of("nickname", "카카오닉")), "id");

    var principal = (LoginUser) socialUserService.toLoginUser("kakao", kakao);

    assertThat(principal.nickname()).isEqualTo("카카오닉");
    assertThat(principal.getName()).isEqualTo(principal.userId().toString());
    assertThat(principal.getAttributes()).containsOnlyKeys("userId");
  }

  // ── 예외 처리 ─────────────────────────────────────────────

  @Test
  void unknownProviderIs404NotServerError() throws Exception {
    mvc.perform(get("/oauth2/authorization/facebook"))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOT_FOUND"));
  }

  @Test
  void unusableProviderResponseBecomesLoginFailure() {
    var noId =
        new DefaultOAuth2User(
            List.of(),
            Map.of("properties", Map.of("nickname", "닉"), "connected_at", "x"),
            "connected_at");

    assertThatThrownBy(() -> socialUserService.toLoginUser("kakao", noId))
        .isInstanceOf(OAuth2AuthenticationException.class)
        .extracting(e -> ((OAuth2AuthenticationException) e).getError().getErrorCode())
        .isEqualTo(SocialOAuth2UserService.INVALID_SOCIAL_PROFILE);
  }

  @Test
  void loginFailureGoesToFrontendWithReason() throws Exception {
    var response = new MockHttpServletResponse();
    var error =
        new OAuth2AuthenticationException(
            new org.springframework.security.oauth2.core.OAuth2Error(
                SocialOAuth2UserService.SOCIAL_LOGIN_FAILED));

    var request = new MockHttpServletRequest();
    request.getSession(true); // 로그인 시작 때 만든 세션 (OAuth2 state)

    loginFailureHandler.onAuthenticationFailure(request, response, error);

    assertThat(response.getRedirectedUrl())
        .isEqualTo("http://localhost:3000/login?error=social&reason=social_login_failed");
    assertThat(request.getSession(false)).isNull(); // 실패해도 세션을 남기지 않아요
  }

  @Test
  void refreshIgnoresExpiredOrBrokenBearerHeader() throws Exception {
    // 프론트가 모든 요청에 만료된 access token을 붙여도 재발급은 쿠키로만 확인해요
    String raw = tokens.issue(login("2101")).refreshToken();

    mvc.perform(
            post("/api/auth/refresh")
                .cookie(new Cookie(RefreshTokenCookies.NAME, raw))
                .header("Authorization", "Bearer not-a-jwt"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.accessToken").isNotEmpty());
  }

  @Test
  void withdrawnUsersLeftoverTokenCannotWrite() throws Exception {
    LoginUser user = login("2102");
    String token = bearer(user);
    jdbc.update("delete from account.users where id = ?", user.userId());

    // 쓰기 요청은 회원이 남아 있는지 보고 401
    mvc.perform(post("/api/users/me/withdrawal").header("Authorization", token))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.code").value("UNAUTHENTICATED"));
    // 읽기는 DB를 보지 않아요 (내 정보는 서비스가 401)
    mvc.perform(get("/api/users/me").header("Authorization", token))
        .andExpect(status().isUnauthorized());
  }

  @Test
  void securityErrorsHaveSameShapeAsControllerErrors() throws Exception {
    mvc.perform(get("/api/users/me"))
        .andExpect(jsonPath("$.type").value("https://mujuthaek.kr/problems/unauthenticated"))
        .andExpect(jsonPath("$.title").value("로그인이 필요해요"))
        .andExpect(jsonPath("$.instance").value("/api/users/me"));
  }

  @Test
  void tokenIssueFailureGoesToFrontendInsteadOf500() throws Exception {
    AuthTokenService broken = mock(AuthTokenService.class);
    when(broken.issue(any())).thenThrow(new IllegalStateException("db down"));
    var handler =
        new LoginSuccessHandler(
            broken,
            refreshTokenCookies,
            loginProperties,
            loginFailureHandler,
            withdrawalService,
            mock(SocialUnlinker.class));
    var response = new MockHttpServletResponse();

    handler.onAuthenticationSuccess(
        new MockHttpServletRequest(),
        response,
        new TestingAuthenticationToken(login("2010"), null));

    assertThat(response.getRedirectedUrl())
        .endsWith("/login?error=social&reason=" + LoginSuccessHandler.TOKEN_ISSUE_FAILED);
    assertThat(response.getHeader("Set-Cookie")).isNull(); // refresh token 쿠키를 주지 않아요
  }

  // ── 탈퇴 (재인증 → 회원 삭제 → 소셜 연결 끊기) ─────────────────────

  private LoginSuccessHandler handlerWith(SocialUnlinker unlinker) {
    return new LoginSuccessHandler(
        tokens,
        refreshTokenCookies,
        loginProperties,
        loginFailureHandler,
        withdrawalService,
        unlinker);
  }

  private MockHttpServletResponse finishReauth(
      LoginSuccessHandler handler, WithdrawalPrincipal principal) throws Exception {
    var response = new MockHttpServletResponse();
    handler.onAuthenticationSuccess(
        new MockHttpServletRequest(), response, new TestingAuthenticationToken(principal, null));
    return response;
  }

  @Test
  void startWithdrawalReturnsReauthUrl() throws Exception {
    LoginUser user = login("3101");

    mvc.perform(post("/api/users/me/withdrawal").header("Authorization", bearer(user)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.provider").value("KAKAO"))
        .andExpect(jsonPath("$.expiresIn").value(600))
        .andExpect(
            jsonPath("$.reauthUrl")
                .value(
                    org.hamcrest.Matchers.startsWith(
                        "http://localhost/oauth2/authorization/kakao?withdraw=")));
    mvc.perform(
            post("/api/users/me/withdrawal")
                .header("Authorization", bearer(user))
                .param("provider", "google"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("WITHDRAWAL_PROVIDER_NOT_LINKED"));
    mvc.perform(post("/api/users/me/withdrawal")).andExpect(status().isUnauthorized());
  }

  /** 발급하는 티켓과 같은 모양(43자 URL Base64). */
  private static String ticketLike(char c) {
    return String.valueOf(c).repeat(43);
  }

  @Test
  void reauthStartForcesLoginAndMarksSession() throws Exception {
    String ticket1 = ticketLike('a');
    var naver =
        mvc.perform(get("/oauth2/authorization/naver").param("withdraw", ticket1))
            .andExpect(status().is3xxRedirection())
            .andReturn();
    assertThat(naver.getResponse().getRedirectedUrl())
        .contains("auth_type=reauthenticate")
        .doesNotContain(ticket1);
    assertThat(WithdrawalSession.ticket(naver.getRequest())).contains(ticket1);

    var kakao =
        mvc.perform(get("/oauth2/authorization/kakao").param("withdraw", ticketLike('b')))
            .andReturn();
    assertThat(kakao.getResponse().getRedirectedUrl()).contains("prompt=login");
    var google =
        mvc.perform(get("/oauth2/authorization/google").param("withdraw", ticketLike('c')))
            .andReturn();
    assertThat(google.getResponse().getRedirectedUrl()).contains("prompt=select_account");

    var normal = mvc.perform(get("/oauth2/authorization/kakao")).andReturn(); // 일반 로그인은 그대로
    assertThat(normal.getResponse().getRedirectedUrl()).doesNotContain("prompt=");
    assertThat(WithdrawalSession.ticket(normal.getRequest())).isEmpty();
  }

  @Test
  void reauthStartWithAMalformedTicketMakesNoSession() throws Exception {
    // 2026-11-10 코드 검토: 인증 없이 부르는 로그인 시작이 티켓을 길이 검사 없이 세션에 넣어, 큰 값(폼 본문 2MB까지)을 되풀이해 메모리를 채울 수 있었음
    for (String bad :
        new String[] {"x".repeat(100_000), "ticket-1", ticketLike('a') + "=", "가".repeat(43)}) {
      var result =
          mvc.perform(get("/oauth2/authorization/kakao").param("withdraw", bad))
              .andExpect(status().isNotFound())
              .andReturn();
      assertThat(result.getRequest().getSession(false)).isNull();
    }
    var posted =
        mvc.perform(
                post("/oauth2/authorization/kakao")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .content("withdraw=" + "y".repeat(200_000)))
            .andExpect(status().is4xxClientError()) // 로그인 시작이 아니라 없는 주소(POST라 404나 405)
            .andReturn();
    assertThat(posted.getRequest().getSession(false)).isNull();
  }

  @Test
  void withdrawalDeletesUserThenUnlinks() throws Exception {
    LoginUser user = login("3102");
    String refresh = tokens.issue(user).refreshToken();
    String accessBeforeWithdrawal = bearer(user);
    String ticket = withdrawalService.start(user.userId(), null).ticket();
    SocialUnlinker unlinker = mock(SocialUnlinker.class);

    var response =
        finishReauth(
            handlerWith(unlinker),
            new WithdrawalPrincipal(SocialProvider.KAKAO, "3102", ticket, "kakao-token"));

    assertThat(response.getRedirectedUrl()).isEqualTo("http://localhost:3000/withdrawn");
    assertThat(response.getHeader("Set-Cookie")).contains("Max-Age=0"); // refresh token 쿠키 삭제
    assertThat(users.findById(user.userId())).isEmpty();
    verify(unlinker).unlink(SocialProvider.KAKAO, "kakao-token");
    mvc.perform(post("/api/auth/refresh").cookie(new Cookie(RefreshTokenCookies.NAME, refresh)))
        .andExpect(status().isUnauthorized());
    mvc.perform(
            get("/api/users/me")
                .header("Authorization", accessBeforeWithdrawal)) // 탈퇴 전에 받은 access token
        .andExpect(status().isUnauthorized());
  }

  @Test
  void unlinkFailureStillCompletesWithdrawal() throws Exception {
    LoginUser user = login("3103");
    String ticket = withdrawalService.start(user.userId(), null).ticket();
    SocialUnlinker unlinker = mock(SocialUnlinker.class);
    doThrow(new IllegalStateException("provider down")).when(unlinker).unlink(any(), any());

    var response =
        finishReauth(
            handlerWith(unlinker),
            new WithdrawalPrincipal(SocialProvider.KAKAO, "3103", ticket, "t"));

    assertThat(response.getRedirectedUrl()).endsWith("/withdrawn");
    assertThat(users.findById(user.userId())).isEmpty();
  }

  @Test
  void reauthWithOtherAccountDoesNotWithdraw() throws Exception {
    LoginUser user = login("3104");
    login("3105");
    String ticket = withdrawalService.start(user.userId(), null).ticket();
    SocialUnlinker unlinker = mock(SocialUnlinker.class);

    var response =
        finishReauth(
            handlerWith(unlinker),
            new WithdrawalPrincipal(SocialProvider.KAKAO, "3105", ticket, "t"));

    assertThat(response.getRedirectedUrl())
        .isEqualTo("http://localhost:3000/mypage?withdraw=account_mismatch");
    assertThat(users.findById(user.userId())).isPresent();
    verify(unlinker, never()).unlink(any(), any());
  }

  @Test
  void unknownOrUsedTicketDoesNotWithdraw() throws Exception {
    LoginUser user = login("3106");
    SocialUnlinker unlinker = mock(SocialUnlinker.class);

    var response =
        finishReauth(
            handlerWith(unlinker),
            new WithdrawalPrincipal(SocialProvider.KAKAO, "3106", "made-up", "t"));

    assertThat(response.getRedirectedUrl())
        .isEqualTo("http://localhost:3000/mypage?withdraw=expired");
    assertThat(users.findById(user.userId())).isPresent();
    verify(unlinker, never()).unlink(any(), any());
  }

  @Test
  void cancelDuringReauthGoesBackToMypage() throws Exception {
    var request = new MockHttpServletRequest();
    WithdrawalSession.start(request, "ticket");
    var response = new MockHttpServletResponse();
    var denied =
        new OAuth2AuthenticationException(
            new org.springframework.security.oauth2.core.OAuth2Error("access_denied"));

    loginFailureHandler.onAuthenticationFailure(request, response, denied);

    assertThat(response.getRedirectedUrl())
        .isEqualTo("http://localhost:3000/mypage?withdraw=cancelled");
  }

  @Test
  void reauthCallbackBuildsWithdrawalPrincipalWithoutLogin() {
    var naver =
        new DefaultOAuth2User(
            List.of(), Map.of("response", Map.of("id", "nv-reauth", "nickname", "닉")), "response");

    var principal =
        (WithdrawalPrincipal)
            socialUserService.toWithdrawalPrincipal("naver", naver, "ticket", "naver-token");

    assertThat(principal.provider()).isEqualTo(SocialProvider.NAVER);
    assertThat(principal.providerUserId()).isEqualTo("nv-reauth");
    assertThat(principal.toString())
        .doesNotContain("naver-token")
        .doesNotContain("ticket"); // 로그에 토큰·티켓이 안 남게
  }
}
