package kr.mujuthaek.api;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

// 운영 compose의 API_DOCS_ENABLED=false는 프로필과 상관없이 문서를 꺼요. 프로필 설정이 빠져 기본 local(문서 켬)로 떠도 꺼지는지 봐요
@SpringBootTest(
    properties = {"spring.rabbitmq.listener.simple.auto-startup=false", "API_DOCS_ENABLED=false"})
@AutoConfigureMockMvc
@Import(TestcontainersConfiguration.class)
class ApiDocsDisabledByEnvTest {

  @Autowired MockMvc mvc;

  @Test
  void 환경_변수로_끄면_local_프로필에서도_문서와_화면이_없다() throws Exception {
    mvc.perform(get("/v3/api-docs/user")).andExpect(status().isNotFound());
    mvc.perform(get("/swagger-ui/index.html")).andExpect(status().isNotFound());
    mvc.perform(get("/webjars/swagger-ui/index.html")).andExpect(status().isNotFound());
  }
}
