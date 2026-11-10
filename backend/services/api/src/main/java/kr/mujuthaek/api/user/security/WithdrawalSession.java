package kr.mujuthaek.api.user.security;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import java.util.Optional;

/**
 * 재인증(소셜 다시 로그인) 동안 "이 로그인은 탈퇴용"이라는 표시와 티켓을 로그인 중간 세션에 둬요. 로그인 시작(state 저장)과 같은 세션이라 콜백에서 꺼낼 수 있고,
 * 로그인이 끝나면 세션째 지워져요.
 */
final class WithdrawalSession {

  static final String PARAM = "withdraw";
  private static final String ATTRIBUTE = WithdrawalSession.class.getName() + ".ticket";

  private WithdrawalSession() {}

  static void start(HttpServletRequest request, String ticket) {
    request.getSession(true).setAttribute(ATTRIBUTE, ticket);
  }

  /** 일반 로그인으로 시작하면 예전 탈퇴 표시를 지워요 (탈퇴하려다 그만두고 그냥 로그인한 경우). */
  static void clear(HttpServletRequest request) {
    HttpSession session = request.getSession(false);
    if (session != null) {
      session.removeAttribute(ATTRIBUTE);
    }
  }

  static Optional<String> ticket(HttpServletRequest request) {
    HttpSession session = request.getSession(false);
    return Optional.ofNullable(session == null ? null : (String) session.getAttribute(ATTRIBUTE));
  }
}
