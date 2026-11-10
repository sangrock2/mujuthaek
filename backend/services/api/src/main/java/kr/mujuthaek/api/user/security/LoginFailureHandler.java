package kr.mujuthaek.api.user.security;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.stereotype.Component;

/**
 * 카카오 로그인 실패: 원인을 로그에 남기고 프론트 로그인 화면으로 돌려보내요. 주소의 reason은 OAuth2 오류 코드예요 (예: invalid_token_response
 * = 토큰 교환 실패(Client Secret·Redirect URI 확인), access_denied = 사용자가 동의 취소,
 * authorization_request_not_found = 로그인 시작과 콜백의 세션이 달라짐). 탈퇴 재인증 중이면 마이페이지로 보내요 ({@code
 * ?withdraw=cancelled|failed}).
 */
@Component
class LoginFailureHandler implements AuthenticationFailureHandler {

  private static final Logger log = LoggerFactory.getLogger(LoginFailureHandler.class);

  private final LoginProperties props;

  LoginFailureHandler(LoginProperties props) {
    this.props = props;
  }

  @Override
  public void onAuthenticationFailure(
      HttpServletRequest request, HttpServletResponse response, AuthenticationException error)
      throws IOException {
    String reason =
        error instanceof OAuth2AuthenticationException oauth
            ? oauth.getError().getErrorCode()
            : error.getClass().getSimpleName();
    if (WithdrawalSession.ticket(request).isPresent()) { // 탈퇴 재인증 중 실패·취소 → 탈퇴하지 않고 마이페이지로
      log.warn("탈퇴 재인증 실패: reason={}, detail={}", reason, error.getMessage());
      request.getSession().invalidate();
      response.sendRedirect(
          props.frontendUrl()
              + "/mypage?withdraw="
              + ("access_denied".equals(reason) ? "cancelled" : "failed"));
      return;
    }
    log.warn("소셜 로그인 실패: reason={}, detail={}", reason, error.getMessage(), error);
    // 로그인 시작 때 만든 세션(OAuth2 state 등)을 남기지 않아요. 실패·봇 요청마다 만료될 때까지 메모리에 쌓여요
    HttpSession session = request.getSession(false);
    if (session != null) {
      session.invalidate();
    }
    response.sendRedirect(
        props.frontendUrl()
            + "/login?error=social&reason="
            + URLEncoder.encode(reason, StandardCharsets.UTF_8));
  }
}
