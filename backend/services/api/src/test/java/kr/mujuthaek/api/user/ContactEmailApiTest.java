package kr.mujuthaek.api.user;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.Map;
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
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

/** 연락용 이메일 API: 등록·변경·삭제, 동의 기록, 검사, 로그인. */
@SpringBootTest
@AutoConfigureMockMvc
@Import(TestcontainersConfiguration.class)
class ContactEmailApiTest {

  @Autowired MockMvc mvc;
  @Autowired SocialLoginService logins;
  @Autowired AuthTokenService tokens;
  @Autowired JdbcClient jdbc;

  @Test
  void needsLogin() throws Exception {
    mvc.perform(
            put("/api/users/me/email")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"a@example.com\",\"consentVersion\":\"email-v1\"}"))
        .andExpect(status().isUnauthorized());
    mvc.perform(delete("/api/users/me/email")).andExpect(status().isUnauthorized());
  }

  /** 프론트(FRONTEND_URL, 로컬 3000)에서 다른 포트의 api로 PUT·DELETE를 보낼 때 브라우저가 먼저 묻는 요청 */
  @Test
  void browserPreflightFromFrontendIsAllowed() throws Exception {
    for (String method : new String[] {"PUT", "DELETE"}) {
      mvc.perform(
              options("/api/users/me/email")
                  .header("Origin", "http://localhost:3000")
                  .header("Access-Control-Request-Method", method)
                  .header("Access-Control-Request-Headers", "authorization,content-type"))
          .andExpect(status().isOk())
          .andExpect(header().string("Access-Control-Allow-Origin", "http://localhost:3000"))
          .andExpect(header().string("Access-Control-Allow-Credentials", "true"));
    }
    mvc.perform(
            options("/api/users/me/email")
                .header("Origin", "https://evil.example")
                .header("Access-Control-Request-Method", "PUT"))
        .andExpect(status().isForbidden());
  }

  @Test
  void emailIsOptionalSavedWithConsentAndRemoved() throws Exception {
    LoginUser me = login();
    mvc.perform(as(me, get("/api/users/me")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.email").doesNotExist());

    mvc.perform(
            as(me, put("/api/users/me/email"))
                .content("{\"email\":\"  Hong.Gil@Example.COM \",\"consentVersion\":\"email-v1\"}"))
        .andExpect(status().isNoContent());
    // 도메인만 소문자로, 앞뒤 공백은 빼요
    mvc.perform(as(me, get("/api/users/me")))
        .andExpect(jsonPath("$.email").value("Hong.Gil@example.com"));
    Map<String, Object> row = consent(me);
    assertThat(row.get("email_consent_version")).isEqualTo("email-v1");
    assertThat(row.get("email_consented_at")).isNotNull();

    // 마이페이지에서 바꾸기: 새 동의 버전으로
    mvc.perform(
            as(me, put("/api/users/me/email"))
                .content("{\"email\":\"new@example.com\",\"consentVersion\":\"email-v2\"}"))
        .andExpect(status().isNoContent());
    mvc.perform(as(me, get("/api/users/me")))
        .andExpect(jsonPath("$.email").value("new@example.com"));
    assertThat(consent(me).get("email_consent_version")).isEqualTo("email-v2");

    // 지우면 동의 기록도 같이 비워요. 다시 지워도 204
    mvc.perform(as(me, delete("/api/users/me/email"))).andExpect(status().isNoContent());
    mvc.perform(as(me, delete("/api/users/me/email"))).andExpect(status().isNoContent());
    mvc.perform(as(me, get("/api/users/me"))).andExpect(jsonPath("$.email").doesNotExist());
    row = consent(me);
    assertThat(row.get("email_consent_version")).isNull();
    assertThat(row.get("email_consented_at")).isNull();
  }

  @Test
  void badEmailOrConsentIs400WithoutEchoingTheAddress() throws Exception {
    LoginUser me = login();
    for (String email : new String[] {"not-an-email", "a@b", "a b@example.com", "a@@example.com"}) {
      mvc.perform(
              as(me, put("/api/users/me/email"))
                  .content("{\"email\":\"" + email + "\",\"consentVersion\":\"email-v1\"}"))
          .andExpect(status().isBadRequest())
          .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
          .andExpect(jsonPath("$.detail").value("email: 이메일 주소 형식이 아니에요"));
    }
    String tooLong = "a".repeat(64) + "@" + "b".repeat(186) + ".com"; // 255자
    mvc.perform(
            as(me, put("/api/users/me/email"))
                .content("{\"email\":\"" + tooLong + "\",\"consentVersion\":\"email-v1\"}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.detail").value("email: 254자를 넘어요"));

    // 동의 문구 버전 없이는 저장하지 않아요 (선택 항목이라 동의가 근거)
    mvc.perform(as(me, put("/api/users/me/email")).content("{\"email\":\"a@example.com\"}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
    mvc.perform(
            as(me, put("/api/users/me/email"))
                .content("{\"email\":\"a@example.com\",\"consentVersion\":\"동의 v1\"}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.detail").value("consentVersion: 영문·숫자·점·하이픈으로 20자까지예요"));
    mvc.perform(as(me, get("/api/users/me"))).andExpect(jsonPath("$.email").doesNotExist());
  }

  @Test
  void brokenBodiesAre400Not500() throws Exception {
    LoginUser me = login();
    String[] bodies = {
      "", // 본문 없음
      "{\"email\":", // JSON이 깨짐
      "{\"email\":{\"a\":1},\"consentVersion\":\"email-v1\"}", // 문자열이 아님
      "{\"email\":\"a\\u0000b@example.com\",\"consentVersion\":\"email-v1\"}", // NUL (DB가 못 받아요)
      "{\"email\":\"a\\u0007b@example.com\",\"consentVersion\":\"email-v1\"}", // 다른 제어 문자
      "{\"email\":\"a@example.com.\",\"consentVersion\":\"email-v1\"}", // 끝이 점
      "{\"email\":\"a\\u3000b@example.com\",\"consentVersion\":\"email-v1\"}", // 전각 공백
      "{\"email\":\"a@exam\\u00a0ple.com\",\"consentVersion\":\"email-v1\"}", // 줄바꿈 없는 공백
      "{\"email\":\""
          + "a".repeat(65)
          + "@example.com\",\"consentVersion\":\"email-v1\"}", // 아이디 65자
    };
    for (String body : bodies) {
      mvc.perform(as(me, put("/api/users/me/email")).content(body))
          .andExpect(status().isBadRequest());
    }
    mvc.perform(as(me, get("/api/users/me"))).andExpect(jsonPath("$.email").doesNotExist());
  }

  @Test
  void unicodeAndLongestAddressesAreKept() throws Exception {
    LoginUser me = login();
    String longest = "a".repeat(64) + "@" + "b".repeat(185) + ".com"; // 254자
    mvc.perform(
            as(me, put("/api/users/me/email"))
                .content("{\"email\":\"" + longest + "\",\"consentVersion\":\"email-v1\"}"))
        .andExpect(status().isNoContent());
    mvc.perform(as(me, get("/api/users/me"))).andExpect(jsonPath("$.email").value(longest));

    mvc.perform(
            as(me, put("/api/users/me/email"))
                .content("{\"email\":\"홍길동@회사.한국\",\"consentVersion\":\"email-v1\"}"))
        .andExpect(status().isNoContent());
    mvc.perform(as(me, get("/api/users/me"))).andExpect(jsonPath("$.email").value("홍길동@회사.한국"));
  }

  @Test
  void withdrawnUserCannotSaveWithLeftoverToken() throws Exception {
    LoginUser me = login();
    String token = tokens.issue(me).accessToken();
    jdbc.sql("delete from account.users where id = :id").param("id", me.userId()).update();
    mvc.perform(
            put("/api/users/me/email")
                .header("Authorization", "Bearer " + token)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"a@example.com\",\"consentVersion\":\"email-v1\"}"))
        .andExpect(status().isUnauthorized());
  }

  @Test
  void anAddressBelongsToOneMemberIgnoringCase() throws Exception {
    LoginUser a = login();
    LoginUser b = login();
    String address = "dup-" + UUID.randomUUID() + "@example.com";
    mvc.perform(as(a, put("/api/users/me/email")).content(body(address)))
        .andExpect(status().isNoContent());

    // 다른 회원은 같은 주소·대소문자만 다른 주소를 못 써요
    mvc.perform(as(b, put("/api/users/me/email")).content(body(address)))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("EMAIL_ALREADY_USED"));
    mvc.perform(as(b, put("/api/users/me/email")).content(body(address.toUpperCase())))
        .andExpect(status().isConflict());
    mvc.perform(as(b, get("/api/users/me"))).andExpect(jsonPath("$.email").doesNotExist());

    // 본인은 같은 주소로 다시 저장할 수 있어요 (동의 다시 받기)
    mvc.perform(as(a, put("/api/users/me/email")).content(body(address.toUpperCase())))
        .andExpect(status().isNoContent());

    // 지우면 다른 회원이 쓸 수 있어요
    mvc.perform(as(a, delete("/api/users/me/email"))).andExpect(status().isNoContent());
    mvc.perform(as(b, put("/api/users/me/email")).content(body(address)))
        .andExpect(status().isNoContent());
  }

  /** 앞의 확인을 지나 동시에 같은 주소를 넣어도 DB 유니크 인덱스가 막아요 */
  @Test
  void uniqueIndexBlocksDuplicatesIgnoringCase() {
    LoginUser a = login();
    LoginUser b = login();
    String address = "race-" + UUID.randomUUID() + "@example.com";
    String sql =
        "update account.users set email = :email, email_consent_version = 'email-v1',"
            + " email_consented_at = now() where id = :id";
    jdbc.sql(sql).param("email", address).param("id", a.userId()).update();
    assertThatThrownBy(
            () ->
                jdbc.sql(sql)
                    .param("email", address.toUpperCase())
                    .param("id", b.userId())
                    .update())
        .hasMessageContaining("users_email_uk");
  }

  private static String body(String email) {
    return "{\"email\":\"" + email + "\",\"consentVersion\":\"email-v1\"}";
  }

  private Map<String, Object> consent(LoginUser user) {
    return jdbc.sql(
            "select email_consent_version, email_consented_at from account.users where id = :id")
        .param("id", user.userId())
        .query()
        .singleRow();
  }

  private MockHttpServletRequestBuilder as(LoginUser user, MockHttpServletRequestBuilder request) {
    return request
        .header("Authorization", "Bearer " + tokens.issue(user).accessToken())
        .contentType(MediaType.APPLICATION_JSON);
  }

  private LoginUser login() {
    return logins.login(
        new SocialProfile(SocialProvider.KAKAO, "email-" + UUID.randomUUID(), "닉네임"));
  }
}
