package kr.mujuthaek.notification.support;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

/** /actuator/prometheus 문지기 (2026-11-16 보안 감사 4장). 컨테이너 망 안의 다른 컨테이너가 지표를 읽지 못하게 해요. */
class MetricsAccessFilterTest {

  private static final String SCRAPE_TOKEN = "scrape-token-for-test";

  private static MockHttpServletResponse call(MetricsAccessFilter filter, String authorization)
      throws Exception {
    var request = new MockHttpServletRequest("GET", "/actuator/prometheus");
    if (authorization != null) {
      request.addHeader("Authorization", authorization);
    }
    var response = new MockHttpServletResponse();
    var chain = new MockFilterChain();
    filter.doFilter(request, response, chain);
    if (chain.getRequest() != null) {
      response.setStatus(200); // 다음 단계(지표)까지 갔어요
    }
    return response;
  }

  @Test
  void withATokenOnlyTheMatchingBearerPasses() throws Exception {
    var filter = new MetricsAccessFilter(SCRAPE_TOKEN, true);

    assertThat(call(filter, "Bearer " + SCRAPE_TOKEN).getStatus()).isEqualTo(200);
    assertThat(call(filter, "bearer " + SCRAPE_TOKEN).getStatus()).isEqualTo(200);
    assertThat(call(filter, null).getStatus()).isEqualTo(401);
    assertThat(call(filter, "Bearer wrong").getStatus()).isEqualTo(401);
    assertThat(call(filter, SCRAPE_TOKEN).getStatus()).isEqualTo(401);
    assertThat(call(filter, null).getHeader("WWW-Authenticate")).isEqualTo("Bearer");
  }

  @Test
  void withoutATokenProductionHidesTheEndpoint() throws Exception {
    assertThat(call(new MetricsAccessFilter("", true), null).getStatus()).isEqualTo(404);
    assertThat(call(new MetricsAccessFilter("  ", true), "Bearer  ").getStatus()).isEqualTo(404);
  }

  @Test
  void withoutATokenLocalKeepsItOpen() throws Exception {
    assertThat(call(new MetricsAccessFilter(null, false), null).getStatus()).isEqualTo(200);
  }
}
