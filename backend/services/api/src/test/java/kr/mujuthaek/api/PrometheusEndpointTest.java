package kr.mujuthaek.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

// 성능 테스트는 서버 쪽 p95·p99를 이 지표의 히스토그램으로 계산해요. 테스트에선 내보내기가 꺼져 있어 켜고 봐요
@SpringBootTest(
    properties = {
      "spring.rabbitmq.listener.simple.auto-startup=false",
      "management.defaults.metrics.export.enabled=true"
    })
@AutoConfigureMockMvc
@Import(TestcontainersConfiguration.class)
class PrometheusEndpointTest {

  @Autowired MockMvc mvc;

  @Test
  void exposesRequestHistogramAndPoolMetrics() throws Exception {
    mvc.perform(get("/api/v1/regions"));

    String body =
        mvc.perform(get("/actuator/prometheus"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

    assertThat(body)
        .contains("http_server_requests_seconds_bucket{")
        .contains("hikaricp_connections_pending")
        .contains("jvm_memory_used_bytes");
  }
}
