package kr.mujuthaek.api.user.security;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import java.io.IOException;
import java.util.UUID;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.user.service.AuthTokenService;
import kr.mujuthaek.api.user.service.LoginUser;
import kr.mujuthaek.api.user.service.TokenPair;
import kr.mujuthaek.api.user.service.WithdrawalService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.stereotype.Component;

/**
 * 소셜 로그인 성공 뒤.
 *
 * <ul>
 *   <li>로그인: refresh token을 HttpOnly 쿠키로 주고 프론트 {@code /auth/callback}으로 돌려보내요(처음 가입이면 {@code
 *       ?new=1}). access token은 주소에 싣지 않아요(브라우저 기록·로그에 남음). 프론트는 돌아오자마자 {@code POST
 *       /api/auth/refresh}로 access token을 받아요. 토큰 발급이 실패하면 실패 처리기로 넘겨요.
 *   <li>탈퇴 재인증: 티켓 확인 → 계정 일치 확인·회원 삭제(커밋) → 소셜 연결 끊기 → {@code FRONTEND_URL/withdrawn}. 실패하면 {@code
 *       FRONTEND_URL/mypage?withdraw=expired|account_mismatch|failed}.
 * </ul>
 */
@Component
class LoginSuccessHandler implements AuthenticationSuccessHandler {

  static final String TOKEN_ISSUE_FAILED = "token_issue_failed";

  /** 이용 정지된 회원: 프론트 /login?error=social&reason=suspended */
  static final String SUSPENDED = "suspended";

  /** 로그인 뒤 돌아갈 프론트 화면. 처음 가입이면 ?new=1 (프론트가 약관 동의 화면으로 보내요) */
  static final String CALLBACK_PATH = "/auth/callback";

  private static final Logger log = LoggerFactory.getLogger(LoginSuccessHandler.class);

  private final AuthTokenService tokens;
  private final RefreshTokenCookies cookies;
  private final LoginProperties props;
  private final LoginFailureHandler failureHandler;
  private final WithdrawalService withdrawals;
  private final SocialUnlinker unlinker;

  LoginSuccessHandler(
      AuthTokenService tokens,
      RefreshTokenCookies cookies,
      LoginProperties props,
      LoginFailureHandler failureHandler,
      WithdrawalService withdrawals,
      SocialUnlinker unlinker) {
    this.tokens = tokens;
    this.cookies = cookies;
    this.props = props;
    this.failureHandler = failureHandler;
    this.withdrawals = withdrawals;
    this.unlinker = unlinker;
  }

  @Override
  public void onAuthenticationSuccess(
      HttpServletRequest request, HttpServletResponse response, Authentication auth)
      throws IOException, ServletException {
    clearLoginSession(request); // 로그인 중간(state·탈퇴 표시 저장)에만 쓴 세션
    if (auth.getPrincipal() instanceof WithdrawalPrincipal withdrawal) {
      withdraw(response, withdrawal);
      return;
    }
    TokenPair pair;
    try {
      pair = tokens.issue((LoginUser) auth.getPrincipal());
    } catch (RuntimeException e) {
      String code =
          e instanceof CustomException c && c.errorCode() == ErrorCode.ACCOUNT_SUSPENDED
              ? SUSPENDED
              : TOKEN_ISSUE_FAILED;
      var error = new OAuth2Error(code, e.getMessage(), null);
      failureHandler.onAuthenticationFailure(
          request, response, new OAuth2AuthenticationException(error, e.getMessage(), e));
      return;
    }
    cookies.write(response, pair.refreshToken(), pair.refreshTokenTtl());
    boolean joined =
        Boolean.TRUE.equals(request.getAttribute(SocialOAuth2UserService.JOINED_ATTRIBUTE));
    response.sendRedirect(props.frontendUrl() + CALLBACK_PATH + (joined ? "?new=1" : ""));
  }

  /** 순서: 우리 DB 삭제가 먼저 커밋돼야 연결을 끊어요. 연결 끊기가 실패해도 탈퇴는 끝난 상태로 두고 로그만 남겨요. */
  private void withdraw(HttpServletResponse response, WithdrawalPrincipal withdrawal)
      throws IOException {
    UUID userId;
    try {
      userId = withdrawals.consume(withdrawal.ticket(), withdrawal.provider());
      withdrawals.withdraw(userId, withdrawal.provider(), withdrawal.providerUserId());
    } catch (CustomException e) {
      String reason =
          e.errorCode() == ErrorCode.WITHDRAWAL_ACCOUNT_MISMATCH ? "account_mismatch" : "expired";
      log.warn("탈퇴 중단: reason={}, provider={}", reason, withdrawal.provider());
      response.sendRedirect(props.frontendUrl() + "/mypage?withdraw=" + reason);
      return;
    } catch (RuntimeException e) {
      log.error("탈퇴 실패: provider={}", withdrawal.provider(), e);
      response.sendRedirect(props.frontendUrl() + "/mypage?withdraw=failed");
      return;
    }
    try {
      unlinker.unlink(withdrawal.provider(), withdrawal.providerAccessToken());
    } catch (RuntimeException e) {
      log.warn(
          "소셜 연결 끊기 실패 (탈퇴는 완료): userId={}, provider={}, detail={}",
          userId,
          withdrawal.provider(),
          e.getMessage());
    }
    log.info("회원 탈퇴: userId={}, provider={}", userId, withdrawal.provider());
    cookies.clear(response);
    response.sendRedirect(props.frontendUrl() + "/withdrawn");
  }

  private static void clearLoginSession(HttpServletRequest request) {
    HttpSession session = request.getSession(false);
    if (session != null) {
      session.invalidate();
    }
  }
}
