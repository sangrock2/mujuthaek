package kr.mujuthaek.api.user;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import java.util.UUID;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.notification.client.NotificationServerClient;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.service.*;
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
  @Autowired AuthTokenService tokens;
  @Autowired JdbcClient jdbc;
  @MockitoBean NotificationServerClient mail;
  static final String PATH = "/api/users/me/email-notifications";

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
  void verificationIsOwnerBoundSingleUseAndDoesNotEnableUntilConsent() throws Exception {
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
    mvc.perform(as(user, post(PATH + "/verify")).content(token(token)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.verified").value(true))
        .andExpect(jsonPath("$.enabled").value(false));
    mvc.perform(as(user, post(PATH + "/verify")).content(token(token)))
        .andExpect(status().isBadRequest());
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
  void deleteStopsDeliveryAndCannotResetResendLimit() throws Exception {
    LoginUser user = login();
    request(user);
    mvc.perform(as(user, delete(PATH))).andExpect(status().isOk());
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
    mvc.perform(as(user, post(PATH + "/verify")).content(token(token)))
        .andExpect(status().isBadRequest());
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
    mvc.perform(as(user, get(PATH))).andExpect(jsonPath("$.enabled").value(false));
  }

  private String request(LoginUser user) throws Exception {
    mvc.perform(
            as(user, post(PATH + "/request"))
                .content("{\"email\":\"verified@example.com\",\"consent\":true}"))
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
    return logins.login(
        new SocialProfile(SocialProvider.KAKAO, "mail-" + UUID.randomUUID(), "이메일 시험"));
  }
}
