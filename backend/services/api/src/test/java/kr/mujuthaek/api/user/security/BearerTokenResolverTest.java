package kr.mujuthaek.api.user.security;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.servlet.http.HttpServletRequest;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.web.filter.ForwardedHeaderFilter;

/** Authorization 헤더를 읽을지는 앱 안 경로로 정해요(재발급·로그아웃 /api/auth/**만 헤더를 읽지 않음). */
class BearerTokenResolverTest {

  @Test
  void aForwardedPrefixDoesNotMakeTheTokenIgnored() throws Exception {
    // 2026-11-10 재검토: 요청 주소로 봐서 X-Forwarded-Prefix: /api/auth를 붙이면 토큰을 읽지 않았음
    var request = new MockHttpServletRequest("GET", "/api/v1/me");
    request.addHeader("Authorization", "Bearer abc");
    request.addHeader("X-Forwarded-Prefix", "/api/auth");
    AtomicReference<HttpServletRequest> seen = new AtomicReference<>();
    new ForwardedHeaderFilter()
        .doFilter(
            request,
            new MockHttpServletResponse(),
            new MockFilterChain() {
              @Override
              public void doFilter(
                  jakarta.servlet.ServletRequest req, jakarta.servlet.ServletResponse res) {
                seen.set((HttpServletRequest) req);
              }
            });

    assertThat(seen.get().getRequestURI()).startsWith("/api/auth/");
    assertThat(SecurityConfig.bearerTokenResolver().resolve(seen.get())).isEqualTo("abc");

    var refresh = new MockHttpServletRequest("POST", "/api/auth/refresh");
    refresh.addHeader("Authorization", "Bearer old");
    assertThat(SecurityConfig.bearerTokenResolver().resolve(refresh)).isNull();
  }
}
