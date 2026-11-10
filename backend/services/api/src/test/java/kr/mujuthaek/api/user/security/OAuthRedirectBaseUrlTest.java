package kr.mujuthaek.api.user.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import kr.mujuthaek.api.TestcontainersConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

/**
 * OAUTH_REDIRECT_BASE_URL이 있으면 콜백 주소(redirect_uri)를 요청 주소가 아니라 그 값으로 만들어요. Vercel rewrites → nginx
 * → api를 거치면 요청 주소가 http·서버 IP가 될 수 있어서예요. 값이 없을 때(요청 주소)는 SecurityIntegrationTest가 봐요.
 */
@SpringBootTest(properties = "OAUTH_REDIRECT_BASE_URL=https://example.vercel.app")
@AutoConfigureMockMvc
@Import(TestcontainersConfiguration.class)
class OAuthRedirectBaseUrlTest {

  @Autowired MockMvc mvc;

  @Test
  void 고정한_주소로_콜백_주소를_만든다() throws Exception {
    for (String provider : new String[] {"google", "kakao", "naver"}) {
      var result =
          mvc.perform(get("/oauth2/authorization/" + provider))
              .andExpect(status().is3xxRedirection())
              .andReturn();
      assertThat(result.getResponse().getRedirectedUrl())
          .as(provider)
          .contains("redirect_uri=https://example.vercel.app/login/oauth2/code/" + provider);
    }
  }
}
