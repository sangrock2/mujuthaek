package kr.mujuthaek.api.user;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import java.util.UUID;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.notification.client.NotificationServerClient;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.service.*;
import kr.mujuthaek.api.user.service.TermsAgreementService;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

@SpringBootTest(properties = "mujuthaek.notification.server.token=test-email-private-token")
@AutoConfigureMockMvc
@Import(TestcontainersConfiguration.class)
class EmailNotificationApiTest {
  @Autowired MockMvc mvc;
  @Autowired SocialLoginService logins;
  @Autowired TermsAgreementService terms;
  @Autowired AuthTokenService tokens;
  @Autowired JdbcClient jdbc;
  @MockitoBean NotificationServerClient mail;
  static final String PATH = "/api/users/me/email-notifications";
  static final String VERIFY_LINK = "/api/email-notifications/verify";

  @Test
  void requiresLoginAndExplicitCollectionConsent() throws Exception {
    mvc.perform(get(PATH)).andExpect(status().isUnauthorized());
    mvc.perform(as(login(), post(PATH + "/request")).content("{\"email\":\"a@example.com\"}"))
        .andExpect(status().isBadRequest());
    mvc.perform(
            post("/internal/email-eligibility")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"userId\":\""
                        + UUID.randomUUID()
                        + "\",\"email\":\"a@example.com\",\"type\":\"NEW_NOTICE\"}"))
        .andExpect(status().isForbidden());
  }

  @Test
  void publicVerificationIsSingleUseAndDoesNotEnableUntilConsent() throws Exception {
    LoginUser user = login();
    String token = request(user);
    String stored =
        jdbc.sql("select token_hash from account.notification_emails where user_id=:u")
            .param("u", user.userId())
            .query(String.class)
            .single();
    assertThat(stored).hasSize(64).isNotEqualTo(token);
    mvc.perform(as(user, put(PATH)).content(settings(true, true)))
        .andExpect(status().isBadRequest());
    mvc.perform(as(login(), post(PATH + "/verify")).content(token(token)))
        .andExpect(status().isBadRequest());
    mvc.perform(verifyLink(token)).andExpect(status().isNoContent());
    mvc.perform(as(user, get(PATH)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.verified").value(true))
        .andExpect(jsonPath("$.enabled").value(false));
    mvc.perform(verifyLink(token)).andExpect(status().isBadRequest());
    mvc.perform(as(user, put(PATH)).content(settings(true, false)))
        .andExpect(status().isBadRequest());
    mvc.perform(as(user, put(PATH)).content(settings(true, true)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.enabled").value(true));
    mvc.perform(as(user, put(PATH)).content(settings(false, false)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.enabled").value(false));
  }

  @Test
  void withdrawalClearsTheAddressAndCannotResetResendLimit() throws Exception {
    LoginUser user = login();
    String token = request(user);
    mvc.perform(as(user, delete(PATH))).andExpect(status().isOk());
    mvc.perform(verifyLink(token)).andExpect(status().isBadRequest());
    mvc.perform(as(user, get(PATH)))
        .andExpect(jsonPath("$.email").doesNotExist())
        .andExpect(jsonPath("$.enabled").value(false));
    mvc.perform(
            as(user, post(PATH + "/request"))
                .content("{\"email\":\"b@example.com\",\"consent\":true}"))
        .andExpect(status().isTooManyRequests());
  }

  @Test
  void expiredVerificationCannotBeUsed() throws Exception {
    LoginUser user = login();
    String token = request(user);
    jdbc.sql(
            "update account.notification_emails set expires_at=now()-interval '1 minute' where user_id=:u")
        .param("u", user.userId())
        .update();
    mvc.perform(verifyLink(token)).andExpect(status().isBadRequest());
  }

  @Test
  void unsubscribeLinkIsSignedAndRevokesQueuedDeliveryEligibility() throws Exception {
    LoginUser user = login();
    String token = request(user);
    mvc.perform(as(user, post(PATH + "/verify")).content(token(token))).andExpect(status().isOk());
    mvc.perform(as(user, put(PATH)).content(settings(true, true))).andExpect(status().isOk());
    var eligibility =
        mvc.perform(
                post("/internal/email-eligibility")
                    .header("X-Notification-Token", "test-email-private-token")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        "{\"userId\":\""
                            + user.userId()
                            + "\",\"email\":\"verified@example.com\",\"type\":\"NEW_NOTICE\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.allowed").value(true))
            .andReturn();
    String body = eligibility.getResponse().getContentAsString();
    String unsubscribe = body.replaceAll(".*\"unsubscribeToken\":\"([^\"]+)\".*", "$1");
    String tampered =
        unsubscribe.substring(0, unsubscribe.length() - 1)
            + (unsubscribe.endsWith("0") ? "1" : "0");
    mvc.perform(
            post("/api/email-notifications/unsubscribe")
                .contentType(MediaType.APPLICATION_JSON)
                .content(token(tampered)))
        .andExpect(status().isBadRequest());
    mvc.perform(
            post("/api/email-notifications/unsubscribe")
                .contentType(MediaType.APPLICATION_JSON)
                .content(token(unsubscribe)))
        .andExpect(status().isOk());
    mvc.perform(as(user, get(PATH)))
        .andExpect(jsonPath("$.email").doesNotExist())
        .andExpect(jsonPath("$.enabled").value(false));
  }

  /** 메일 앱의 「수신 거부」 버튼(RFC 8058): 로그인 없이 폼 POST로 끄고, 서명이 틀리면 400 (2026-11-16 보안 감사 4장). */
  @Test
  void oneClickUnsubscribeFromTheMailHeaderWorksWithoutLogin() throws Exception {
    LoginUser user = login();
    String token = request(user);
    mvc.perform(as(user, post(PATH + "/verify")).content(token(token))).andExpect(status().isOk());
    mvc.perform(as(user, put(PATH)).content(settings(true, true))).andExpect(status().isOk());
    String body =
        mvc.perform(
                post("/internal/email-eligibility")
                    .header("X-Notification-Token", "test-email-private-token")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        "{\"userId\":\""
                            + user.userId()
                            + "\",\"email\":\"verified@example.com\",\"type\":\"NEW_NOTICE\"}"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();
    String unsubscribe = body.replaceAll(".*\"unsubscribeToken\":\"([^\"]+)\".*", "$1");
    String tampered =
        unsubscribe.substring(0, unsubscribe.length() - 1)
            + (unsubscribe.endsWith("0") ? "1" : "0");

    mvc.perform(
            post("/api/email-notifications/unsubscribe/one-click")
                .param("token", tampered)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .content("List-Unsubscribe=One-Click"))
        .andExpect(status().isBadRequest());
    mvc.perform(
            post("/api/email-notifications/unsubscribe/one-click?token=" + unsubscribe)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .content("List-Unsubscribe=One-Click"))
        .andExpect(status().isOk());
    mvc.perform(as(user, get(PATH)))
        .andExpect(jsonPath("$.email").doesNotExist())
        .andExpect(jsonPath("$.enabled").value(false));
  }

  @Test
  void twoAccountsCanVerifyTheSameAddressIndependently() throws Exception {
    LoginUser first = login();
    LoginUser second = login();
    request(first);
    sendRequest(second, "verified@example.com").andExpect(status().isOk());
    var capture = ArgumentCaptor.forClass(String.class);
    verify(mail, times(2)).sendEmailVerification(anyString(), capture.capture());
    var links = capture.getAllValues();
    assertThat(links.get(0)).isNotEqualTo(links.get(1));
    mvc.perform(verifyLink(links.get(0))).andExpect(status().isNoContent());
    mvc.perform(as(first, get(PATH))).andExpect(jsonPath("$.verified").value(true));
    mvc.perform(as(second, get(PATH))).andExpect(jsonPath("$.verified").value(false));
    mvc.perform(verifyLink(links.get(1))).andExpect(status().isNoContent());
    mvc.perform(as(first, delete(PATH))).andExpect(status().isOk());
    mvc.perform(as(second, get(PATH)))
        .andExpect(jsonPath("$.email").value("verified@example.com"))
        .andExpect(jsonPath("$.verified").value(true));
  }

  @Test
  void editingUnlocksTheAddressAndInvalidatesThePendingLink() throws Exception {
    LoginUser user = login();
    String original = request(user);
    sendRequest(user, "changed@example.com").andExpect(status().isConflict());
    mvc.perform(as(user, post(PATH + "/edit")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.email").doesNotExist());
    mvc.perform(verifyLink(original)).andExpect(status().isBadRequest());
    sendRequest(user, "changed@example.com").andExpect(status().isTooManyRequests());
    jdbc.sql(
            "update account.notification_emails set requested_at=now()-interval '2 minutes' where user_id=:id")
        .param("id", user.userId())
        .update();
    sendRequest(user, "changed@example.com").andExpect(status().isOk());
    var capture = ArgumentCaptor.forClass(String.class);
    verify(mail, times(2)).sendEmailVerification(anyString(), capture.capture());
    mvc.perform(verifyLink(capture.getAllValues().get(1))).andExpect(status().isNoContent());
    mvc.perform(as(user, get(PATH)))
        .andExpect(jsonPath("$.email").value("changed@example.com"))
        .andExpect(jsonPath("$.verified").value(true));
  }

  private MockHttpServletRequestBuilder verifyLink(String value) {
    return post(VERIFY_LINK).contentType(MediaType.APPLICATION_JSON).content(token(value));
  }

  private org.springframework.test.web.servlet.ResultActions sendRequest(
      LoginUser user, String address) throws Exception {
    return mvc.perform(
        as(user, post(PATH + "/request"))
            .content("{\"email\":\"" + address + "\",\"consent\":true}"));
  }

  private String request(LoginUser user) throws Exception {
    sendRequest(user, "verified@example.com")
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.verified").value(false));
    var capture = ArgumentCaptor.forClass(String.class);
    verify(mail).sendEmailVerification(anyString(), capture.capture());
    return capture.getValue();
  }

  private static String token(String token) {
    return "{\"token\":\"" + token + "\"}";
  }

  private static String settings(boolean enabled, boolean consent) {
    return "{\"enabled\":"
        + enabled
        + ",\"newNotice\":true,\"deadline\":true,\"reportAnswer\":true,\"consent\":"
        + consent
        + "}";
  }

  private MockHttpServletRequestBuilder as(LoginUser user, MockHttpServletRequestBuilder request) {
    return request
        .header("Authorization", "Bearer " + tokens.issue(user).accessToken())
        .contentType(MediaType.APPLICATION_JSON);
  }

  private LoginUser login() {
    return TermsFixture.agreed(
        terms,
        logins.login(
            new SocialProfile(SocialProvider.KAKAO, "mail-" + UUID.randomUUID(), "이메일 시험")));
  }
}
