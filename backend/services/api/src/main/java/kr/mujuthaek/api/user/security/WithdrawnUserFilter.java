package kr.mujuthaek.api.user.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.user.service.AdminUserService;
import kr.mujuthaek.api.user.service.AuthTokenService;
import kr.mujuthaek.api.user.service.LoginUser;
import kr.mujuthaek.api.user.service.UserService;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * 읽기·쓰기를 모두 검사해 탈퇴·정지·로그아웃 후 남은 access token을 다음 요청부터 거부해요.
 *
 * <p>Bean으로 두면 서블릿 필터로도 따로 등록돼서, SecurityConfig에서 {@code new}로 만들어 보안 필터 안에만 넣어요.
 */
class WithdrawnUserFilter extends OncePerRequestFilter {

  private final UserService users;
  private final AdminUserService admins;
  private final ProblemResponses problems;
  private final AuthTokenService tokens;

  WithdrawnUserFilter(
      UserService users,
      AdminUserService admins,
      ProblemResponses problems,
      AuthTokenService tokens) {
    this.users = users;
    this.admins = admins;
    this.problems = problems;
    this.tokens = tokens;
  }

  @Override
  protected void doFilterInternal(
      HttpServletRequest request, HttpServletResponse response, FilterChain chain)
      throws ServletException, IOException {
    var auth = SecurityContextHolder.getContext().getAuthentication();
    if (auth != null && auth.getPrincipal() instanceof LoginUser user) {
      if (!users.exists(user.userId())) {
        problems.write(request, response, ErrorCode.UNAUTHENTICATED);
        return;
      }
      if (admins.suspended(user.userId())) {
        problems.write(request, response, ErrorCode.ACCOUNT_SUSPENDED);
        return;
      }
      boolean active =
          auth instanceof LoginAuthenticationToken session
              && tokens.activeSession(user.userId(), session.sessionId());
      if (!active) {
        problems.write(request, response, ErrorCode.UNAUTHENTICATED);
        return;
      }
    }
    chain.doFilter(request, response);
  }
}
