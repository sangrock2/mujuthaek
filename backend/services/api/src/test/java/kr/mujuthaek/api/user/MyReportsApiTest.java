package kr.mujuthaek.api.user;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.UUID;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.service.AuthTokenService;
import kr.mujuthaek.api.user.service.LoginUser;
import kr.mujuthaek.api.user.service.SocialLoginService;
import kr.mujuthaek.api.user.service.SocialProfile;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

/** 일반 제보(POST /api/v1/reports)와 내 제보(GET /api/users/me/reports): 로그인, 검사, 내 것만 최근 것부터. */
@SpringBootTest
@AutoConfigureMockMvc
@Import(TestcontainersConfiguration.class)
class MyReportsApiTest {

  @Autowired MockMvc mvc;
  @Autowired SocialLoginService logins;
  @Autowired AuthTokenService tokens;

  @Test
  void generalReportsNeedLoginAndAKnownKind() throws Exception {
    mvc.perform(get("/api/users/me/reports")).andExpect(status().isUnauthorized());
    mvc.perform(
            post("/api/v1/reports")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"field\":\"ETC\",\"note\":\"내용\"}"))
        .andExpect(status().isUnauthorized());
    LoginUser me = login();
    mvc.perform(as(me, post("/api/v1/reports")).content("{\"field\":\"HELLO\",\"note\":\"내용\"}"))
        .andExpect(status().isBadRequest());
    mvc.perform(as(me, post("/api/v1/reports")).content("{\"field\":\"ETC\"}"))
        .andExpect(status().isBadRequest());
  }

  @Test
  void myReportsShowOnlyMineNewestFirst() throws Exception {
    LoginUser me = login();
    LoginUser other = login();
    mvc.perform(
            as(me, post("/api/v1/reports"))
                .content(
                    "{\"field\":\"MISSING_NOTICE\",\"note\":\"마포 청년주택 공고가 없어요\",\"screen\":\"검색\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("NEW"));
    mvc.perform(
            as(me, post("/api/v1/reports"))
                .content(
                    "{\"field\":\"APP_ERROR\",\"note\":\"지도가 안 떠요\",\"screen\":\"오류 화면\",\"currentValue\":\"E-503\"}"))
        .andExpect(status().isOk());
    mvc.perform(
            as(other, post("/api/v1/reports")).content("{\"field\":\"ETC\",\"note\":\"남의 제보\"}"))
        .andExpect(status().isOk());

    mvc.perform(as(me, get("/api/users/me/reports")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items.length()").value(2))
        .andExpect(jsonPath("$.items[0].kind").value("GENERAL"))
        .andExpect(jsonPath("$.items[0].field").value("APP_ERROR"))
        .andExpect(jsonPath("$.items[0].note").value("지도가 안 떠요"))
        .andExpect(jsonPath("$.items[0].status").value("NEW"))
        .andExpect(jsonPath("$.items[0].targetId").doesNotExist())
        .andExpect(jsonPath("$.items[0].linkPath").doesNotExist())
        .andExpect(jsonPath("$.items[1].field").value("MISSING_NOTICE"));
  }

  private MockHttpServletRequestBuilder as(LoginUser user, MockHttpServletRequestBuilder request) {
    return request
        .header("Authorization", "Bearer " + tokens.issue(user).accessToken())
        .contentType(MediaType.APPLICATION_JSON);
  }

  private LoginUser login() {
    return logins.login(
        new SocialProfile(SocialProvider.KAKAO, "report-" + UUID.randomUUID(), "닉네임"));
  }
}
