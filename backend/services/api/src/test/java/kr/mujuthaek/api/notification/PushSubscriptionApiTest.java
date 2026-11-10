package kr.mujuthaek.api.notification;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.security.SecureRandom;
import java.util.Base64;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.service.AuthTokenService;
import kr.mujuthaek.api.user.service.LoginUser;
import kr.mujuthaek.api.user.service.SocialLoginService;
import kr.mujuthaek.api.user.service.SocialProfile;
import kr.mujuthaek.api.user.service.WithdrawalService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

/** 웹 푸시 구독 API: 로그인·등록·옮기기·5대 제한·해제·탈퇴, 그리고 주소·키가 응답·로그에 나오지 않는지. */
@SpringBootTest(properties = "app.push.vapid-public-key=BTestPublicKey")
@AutoConfigureMockMvc
@Import(TestcontainersConfiguration.class)
@ExtendWith(OutputCaptureExtension.class)
class PushSubscriptionApiTest {

  private static final String ME = "/api/users/me/push-subscriptions";
  private static final SecureRandom RANDOM = new SecureRandom();

  @Autowired MockMvc mvc;
  @Autowired SocialLoginService logins;
  @Autowired AuthTokenService tokens;
  @Autowired WithdrawalService withdrawals;
  @Autowired JdbcClient jdbc;

  @Test
  void publicKeyNeedsNoLoginButDevicesDo() throws Exception {
    mvc.perform(get("/api/v1/push/public-key"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.publicKey").value("BTestPublicKey"));
    mvc.perform(get(ME)).andExpect(status().isUnauthorized());
    mvc.perform(subscribe(null, endpoint(), "Chrome")).andExpect(status().isUnauthorized());
  }

  @Test
  void subscribeTwiceKeepsOneDeviceWithNewKeysAndNoSecretsInTheList(CapturedOutput output)
      throws Exception {
    LoginUser me = login();
    String endpoint = endpoint();

    mvc.perform(subscribe(me, endpoint, "Chrome / Android")).andExpect(status().isNoContent());
    String newAuth = key(16);
    mvc.perform(subscribe(me, endpoint, p256dh(), newAuth, "Chrome / Android 2"))
        .andExpect(status().isNoContent());

    String body =
        mvc.perform(get(ME).header("Authorization", bearer(me)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.length()").value(1))
            .andExpect(jsonPath("$[0].userAgent").value("Chrome / Android 2"))
            .andExpect(jsonPath("$[0].id").isNotEmpty())
            .andReturn()
            .getResponse()
            .getContentAsString();
    assertThat(body).doesNotContain(endpoint).doesNotContain(newAuth);
    assertThat(column(endpoint, "auth")).isEqualTo(newAuth);
    assertThat(output)
        .doesNotContain(endpoint)
        .doesNotContain(newAuth)
        .contains("fcm.googleapis.com");
  }

  @Test
  void sameBrowserLoggingInAsAnotherMemberMovesTheDevice() throws Exception {
    LoginUser first = login();
    LoginUser second = login();
    String endpoint = endpoint();

    mvc.perform(subscribe(first, endpoint, "Safari")).andExpect(status().isNoContent());
    mvc.perform(subscribe(second, endpoint, "Safari")).andExpect(status().isNoContent());

    assertThat(devices(first)).isZero();
    assertThat(devices(second)).isEqualTo(1);
  }

  @Test
  void sixthDeviceRemovesTheLeastRecentlyUsedOne() throws Exception {
    LoginUser me = login();
    List<String> endpoints = List.of(endpoint(), endpoint(), endpoint(), endpoint(), endpoint());
    for (String e : endpoints) {
      mvc.perform(subscribe(me, e, null)).andExpect(status().isNoContent());
    }
    mvc.perform(subscribe(me, endpoints.getFirst(), null)); // 첫 기기를 다시 열어서 가장 최근이 됨

    mvc.perform(subscribe(me, endpoint(), null)).andExpect(status().isNoContent());

    assertThat(devices(me)).isEqualTo(5);
    assertThat(exists(endpoints.get(1))).as("가장 오래 안 쓴 두 번째 기기").isFalse();
    assertThat(exists(endpoints.getFirst())).isTrue();
  }

  @Test
  void endpointsOutsidePushServicesAndBrokenKeysAreRejectedWithoutEchoingValues() throws Exception {
    LoginUser me = login();
    String evil = "https://evil.example.com/collect/" + UUID.randomUUID();

    String body =
        mvc.perform(subscribe(me, evil, null))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andReturn()
            .getResponse()
            .getContentAsString();
    assertThat(body).doesNotContain(evil).contains("endpoint");

    mvc.perform(subscribe(me, "http://fcm.googleapis.com/fcm/send/x", null))
        .andExpect(status().isBadRequest());
    mvc.perform(subscribe(me, "https://fcm.googleapis.com.evil.com/x", null))
        .andExpect(status().isBadRequest());
    mvc.perform(subscribe(me, endpoint(), key(33), key(16), null))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.detail").value("keys.p256dh: 길이가 맞지 않아요"));
    mvc.perform(subscribe(me, endpoint(), p256dh(), "not+base64/", null))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.detail").value("keys.auth: base64url 형식이 아니에요"));
    mvc.perform(
            put(ME)
                .header("Authorization", bearer(me))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"endpoint\":\"" + endpoint() + "\"}"))
        .andExpect(status().isBadRequest());
    assertThat(devices(me)).isZero();
  }

  @Test
  void unsubscribeRemovesOnlyMyDevice() throws Exception {
    LoginUser me = login();
    LoginUser other = login();
    String mine = endpoint();
    String theirs = endpoint();
    mvc.perform(subscribe(me, mine, null));
    mvc.perform(subscribe(other, theirs, null));

    mvc.perform(unsubscribe(me, theirs)).andExpect(status().isNoContent());
    assertThat(exists(theirs)).as("다른 회원 기기는 그대로").isTrue();

    mvc.perform(unsubscribe(me, mine)).andExpect(status().isNoContent());
    mvc.perform(unsubscribe(me, mine)).andExpect(status().isNoContent()); // 없어도 204
    assertThat(exists(mine)).isFalse();

    mvc.perform(delete(ME).header("Authorization", bearer(me)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.detail").value("endpoint: 꼭 있어야 해요"));
  }

  @Test
  void scopeAllRemovesEveryDeviceOfMine() throws Exception {
    LoginUser me = login();
    LoginUser other = login();
    mvc.perform(subscribe(me, endpoint(), null));
    mvc.perform(subscribe(me, endpoint(), null));
    mvc.perform(subscribe(other, endpoint(), null));

    mvc.perform(delete(ME).param("scope", "everything").header("Authorization", bearer(me)))
        .andExpect(status().isBadRequest());
    mvc.perform(delete(ME).param("scope", "all").header("Authorization", bearer(me)))
        .andExpect(status().isNoContent());

    assertThat(devices(me)).isZero();
    assertThat(devices(other)).isEqualTo(1);
  }

  @Test
  void removeByIdIs404ForSomeoneElsesDevice() throws Exception {
    LoginUser me = login();
    LoginUser other = login();
    mvc.perform(subscribe(other, endpoint(), null));
    UUID theirs = firstId(other);

    mvc.perform(delete(ME + "/" + theirs).header("Authorization", bearer(me)))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("PUSH_SUBSCRIPTION_NOT_FOUND"));
    mvc.perform(delete(ME + "/" + theirs).header("Authorization", bearer(other)))
        .andExpect(status().isNoContent());
    assertThat(devices(other)).isZero();
  }

  @Test
  void withdrawalRemovesDevicesAndTheLeftoverTokenCannotSubscribeAgain() throws Exception {
    String socialId = "push-" + UUID.randomUUID();
    LoginUser me = logins.login(new SocialProfile(SocialProvider.KAKAO, socialId, "닉네임"));
    String token = bearer(me);
    mvc.perform(subscribe(me, endpoint(), null)).andExpect(status().isNoContent());

    withdrawals.withdraw(me.userId(), SocialProvider.KAKAO, socialId);

    assertThat(devices(me)).isZero();
    mvc.perform(
            put(ME)
                .header("Authorization", token)
                .contentType(MediaType.APPLICATION_JSON)
                .content(json(endpoint(), p256dh(), key(16), null)))
        .andExpect(status().isUnauthorized());
    assertThat(devices(me)).isZero();
  }

  private LoginUser login() {
    return logins.login(
        new SocialProfile(SocialProvider.KAKAO, "push-" + UUID.randomUUID(), "닉네임"));
  }

  private String bearer(LoginUser user) {
    return "Bearer " + tokens.issue(user).accessToken();
  }

  private MockHttpServletRequestBuilder subscribe(
      LoginUser user, String endpoint, String userAgent) {
    return subscribe(user, endpoint, p256dh(), key(16), userAgent);
  }

  private MockHttpServletRequestBuilder subscribe(
      LoginUser user, String endpoint, String p256dh, String auth, String userAgent) {
    var request =
        put(ME)
            .contentType(MediaType.APPLICATION_JSON)
            .content(json(endpoint, p256dh, auth, userAgent));
    return user == null ? request : request.header("Authorization", bearer(user));
  }

  private MockHttpServletRequestBuilder unsubscribe(LoginUser user, String endpoint) {
    return delete(ME)
        .header("Authorization", bearer(user))
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"endpoint\":\"" + endpoint + "\"}");
  }

  private static String json(String endpoint, String p256dh, String auth, String userAgent) {
    return """
        {"endpoint":"%s","keys":{"p256dh":"%s","auth":"%s"}%s}
        """
        .formatted(
            endpoint,
            p256dh,
            auth,
            userAgent == null ? "" : ",\"userAgent\":\"" + userAgent + "\"");
  }

  private static String endpoint() {
    return "https://fcm.googleapis.com/fcm/send/" + UUID.randomUUID();
  }

  /** P-256 압축하지 않은 점 모양 (0x04 + 64바이트) */
  private static String p256dh() {
    byte[] point = new byte[65];
    RANDOM.nextBytes(point);
    point[0] = 0x04;
    return Base64.getUrlEncoder().withoutPadding().encodeToString(point);
  }

  private static String key(int bytes) {
    byte[] b = new byte[bytes];
    RANDOM.nextBytes(b);
    return Base64.getUrlEncoder().withoutPadding().encodeToString(b);
  }

  private long devices(LoginUser user) {
    return jdbc.sql("select count(*) from notification.push_subscriptions where user_id = :u")
        .param("u", user.userId())
        .query(Long.class)
        .single();
  }

  private boolean exists(String endpoint) {
    return jdbc.sql("select count(*) from notification.push_subscriptions where endpoint = :e")
            .param("e", endpoint)
            .query(Long.class)
            .single()
        == 1;
  }

  private String column(String endpoint, String column) {
    return jdbc.sql(
            "select " + column + " from notification.push_subscriptions where endpoint = :e")
        .param("e", endpoint)
        .query(String.class)
        .single();
  }

  private UUID firstId(LoginUser user) {
    return jdbc.sql("select id from notification.push_subscriptions where user_id = :u limit 1")
        .param("u", user.userId())
        .query(UUID.class)
        .single();
  }
}
