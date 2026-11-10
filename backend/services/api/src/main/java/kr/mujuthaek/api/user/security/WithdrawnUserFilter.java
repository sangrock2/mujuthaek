package kr.mujuthaek.api.user.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Set;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.user.service.AdminUserService;
import kr.mujuthaek.api.user.service.LoginUser;
import kr.mujuthaek.api.user.service.UserService;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * 탈퇴한 회원의 남은 access token(최대 accessTokenTtl)으로 쓰기 요청이 들어오면 401로, 이용 정지된 회원이면
 * 403(ACCOUNT_SUSPENDED)으로 막아요. 다른 모듈이 {@code UserWithdrawn}으로 데이터를 지운 뒤에 남은 토큰으로 다시 만들지 못하게요.
 * 읽기(GET·HEAD·OPTIONS)는 DB를 보지 않아요 (요청마다 조회가 늘지 않게).
 *
 * <p>Bean으로 두면 서블릿 필터로도 따로 등록돼서, SecurityConfig에서 {@code new}로 만들어 보안 필터 안에만 넣어요.
 */
class WithdrawnUserFilter extends OncePerRequestFilter {

  private static final Set<String> READ_METHODS = Set.of("GET", "HEAD", "OPTIONS");

  private final UserService users;
  private final AdminUserService admins;
  private final ProblemResponses problems;

  WithdrawnUserFilter(UserService users, AdminUserService admins, ProblemResponses problems) {
    this.users = users;
    this.admins = admins;
    this.problems = problems;
  }

  @Override
  protected void doFilterInternal(
      HttpServletRequest request, HttpServletResponse response, FilterChain chain)
      throws ServletException, IOException {
    var auth = SecurityContextHolder.getContext().getAuthentication();
    if (!READ_METHODS.contains(request.getMethod())
        && auth != null
        && auth.getPrincipal() instanceof LoginUser user) {
      if (!users.exists(user.userId())) {
        problems.write(request, response, ErrorCode.UNAUTHENTICATED);
        return;
      }
      if (admins.suspended(user.userId())) {
        problems.write(request, response, ErrorCode.ACCOUNT_SUSPENDED);
        return;
      }
    }
    chain.doFilter(request, response);
  }
}
