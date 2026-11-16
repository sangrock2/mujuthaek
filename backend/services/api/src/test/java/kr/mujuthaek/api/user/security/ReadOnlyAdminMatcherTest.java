package kr.mujuthaek.api.user.security;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;

/**
 * GET 전용 관리자 규칙은 HEAD에도 걸려야 해요. 스프링 MVC가 GET 핸들러로 HEAD를 실행해서, 빠지면 HEAD가 더 넓은 규칙으로 새요(2026-11-16 보안
 * 감사 4장).
 */
class ReadOnlyAdminMatcherTest {

  private static MockHttpServletRequest request(String method, String path) {
    var request = new MockHttpServletRequest(method, path);
    request.setRequestURI(path);
    request.setServletPath(path);
    return request;
  }

  @Test
  void readOnlyRulesCoverGetAndHead() {
    var matcher = SecurityConfig.readOnly("/api/admin/reviews/queue");

    assertThat(matcher.matches(request("GET", "/api/admin/reviews/queue"))).isTrue();
    assertThat(matcher.matches(request("HEAD", "/api/admin/reviews/queue"))).isTrue();
    assertThat(matcher.matches(request("POST", "/api/admin/reviews/queue"))).isFalse();
    assertThat(matcher.matches(request("GET", "/api/admin/reviews/other"))).isFalse();
  }

  @Test
  void wildcardPathsWork() {
    var matcher = SecurityConfig.readOnly("/api/admin/criteria/*/history");

    assertThat(matcher.matches(request("HEAD", "/api/admin/criteria/a1/history"))).isTrue();
    assertThat(matcher.matches(request("PUT", "/api/admin/criteria/a1/history"))).isFalse();
  }
}
