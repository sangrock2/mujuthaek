package kr.mujuthaek.api.user.security;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import jakarta.servlet.http.Cookie;
import java.util.UUID;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.service.AuthTokenService;
import kr.mujuthaek.api.user.service.SocialLoginService;
import kr.mujuthaek.api.user.service.SocialProfile;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

/** 과거 배포본을 변경하지 않고 동일 HTTP 시나리오로 검사하는 고정 fixture. */
@SpringBootTest
@AutoConfigureMockMvc
@Import(TestcontainersConfiguration.class)
class HistoricalLogoutRegressionTest {
  @Autowired MockMvc mvc;
  @Autowired SocialLoginService logins;
  @Autowired AuthTokenService tokens;

  @Test
  void oldTokenMustNotResumeALoggedOutSession() throws Exception {
    var user = logins.login(new SocialProfile(SocialProvider.KAKAO, "baseline-" + UUID.randomUUID(), "검증"));
    var original = new Cookie(RefreshTokenCookies.NAME, tokens.issue(user).refreshToken());
    var current = mvc.perform(post("/api/auth/refresh").cookie(original))
        .andExpect(status().isOk()).andReturn().getResponse().getCookie(RefreshTokenCookies.NAME);
    mvc.perform(post("/api/auth/logout").cookie(current)).andExpect(status().isNoContent());
    mvc.perform(post("/api/auth/refresh").cookie(original)).andExpect(status().isUnauthorized());
  }
}
