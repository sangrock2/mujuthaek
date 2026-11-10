package kr.mujuthaek.api;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

// 운영(prod 프로필)은 API 문서(스웨거)를 꺼요. 관리자 API 구조까지 밖에 보이지 않게요. 개발 서버는 API_DOCS_ENABLED=true로 켜요
@SpringBootTest(
    properties = {
      "spring.rabbitmq.listener.simple.auto-startup=false",
      "app.jwt.secret=test-only-jwt-secret-0123456789-abcdefghij" // 운영 설정은 JWT_SECRET이 꼭 있어야 해요
    })
@ActiveProfiles("prod")
@AutoConfigureMockMvc
@Import(TestcontainersConfiguration.class)
class ApiDocsDisabledInProdTest {

  @Autowired MockMvc mvc;

  @Test
  void 운영_프로필에서는_문서와_화면이_없다() throws Exception {
    mvc.perform(get("/v3/api-docs")).andExpect(status().isNotFound());
    mvc.perform(get("/v3/api-docs/user")).andExpect(status().isNotFound());
    mvc.perform(get("/swagger-ui/index.html")).andExpect(status().isNotFound());
    mvc.perform(get("/webjars/swagger-ui/index.html")).andExpect(status().isNotFound());
  }
}
