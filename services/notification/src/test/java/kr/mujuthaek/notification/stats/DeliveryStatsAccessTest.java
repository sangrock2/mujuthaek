package kr.mujuthaek.notification.stats;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.servlet.http.HttpServletRequest;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.web.filter.ForwardedHeaderFilter;

/** 내부 통계의 「같은 컴퓨터」 검사는 전달 헤더가 아니라 실제 연결 주소를 봐요. */
class DeliveryStatsAccessTest {

  @Test
  void forwardedHeadersCannotPretendToBeTheSameComputer() throws Exception {
    // 2026-11-10 코드 검토: 운영은 forward-headers-strategy=framework라 다른 컨테이너가 「X-Forwarded-For:
    // 127.0.0.1」로 통과했음
    MockHttpServletRequest request = new MockHttpServletRequest("GET", "/internal/stats");
    request.setRemoteAddr("172.18.0.5");
    request.addHeader("X-Forwarded-For", "127.0.0.1");
    AtomicReference<HttpServletRequest> seen = new AtomicReference<>();
    new ForwardedHeaderFilter()
        .doFilter(
            request,
            new MockHttpServletResponse(),
            (req, res) -> seen.set((HttpServletRequest) req));

    assertThat(seen.get().getRemoteAddr()).isEqualTo("127.0.0.1"); // 전달 헤더가 바꾼 값
    assertThat(DeliveryStatsController.socketAddress(seen.get())).isEqualTo("172.18.0.5");
  }
}
