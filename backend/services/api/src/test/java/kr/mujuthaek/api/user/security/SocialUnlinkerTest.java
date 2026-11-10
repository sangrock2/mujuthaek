package kr.mujuthaek.api.user.security;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import kr.mujuthaek.api.user.domain.SocialProvider;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class SocialUnlinkerTest {

  private MockRestServiceServer server;
  private SocialUnlinker unlinker;

  @BeforeEach
  void setUp() {
    var builder = RestClient.builder();
    server = MockRestServiceServer.bindTo(builder).build();
    var naver =
        ClientRegistration.withRegistrationId("naver")
            .clientId("naver-id")
            .clientSecret("naver-secret")
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .authorizationUri("https://nid.naver.com/oauth2.0/authorize")
            .tokenUri("https://nid.naver.com/oauth2.0/token")
            .build();
    unlinker = new SocialUnlinker(builder, new InMemoryClientRegistrationRepository(naver));
  }

  @Test
  void kakaoUsesUserTokenAsBearer() {
    server
        .expect(requestTo(SocialUnlinker.KAKAO_UNLINK))
        .andExpect(method(HttpMethod.POST))
        .andExpect(header("Authorization", "Bearer kakao-user-token"))
        .andRespond(withSuccess("{\"id\":123}", MediaType.APPLICATION_JSON));

    unlinker.unlink(SocialProvider.KAKAO, "kakao-user-token");
    server.verify();
  }

  @Test
  void naverDeletesTokenWithClientCredentials() {
    server
        .expect(requestTo(SocialUnlinker.NAVER_TOKEN))
        .andExpect(method(HttpMethod.POST))
        .andExpect(
            content()
                .formDataContains(
                    java.util.Map.of(
                        "grant_type", "delete",
                        "client_id", "naver-id",
                        "client_secret", "naver-secret",
                        "access_token", "naver-user-token",
                        "service_provider", "NAVER")))
        .andRespond(
            withSuccess(
                "{\"access_token\":\"naver-user-token\",\"result\":\"success\"}",
                MediaType.APPLICATION_JSON));

    unlinker.unlink(SocialProvider.NAVER, "naver-user-token");
    server.verify();
  }

  @Test
  void naverErrorBodyIsFailure() {
    server
        .expect(requestTo(SocialUnlinker.NAVER_TOKEN))
        .andRespond(
            withSuccess(
                "{\"error\":\"invalid_request\"}", MediaType.APPLICATION_JSON)); // 네이버는 실패도 200

    assertThatThrownBy(() -> unlinker.unlink(SocialProvider.NAVER, "t"))
        .isInstanceOf(IllegalStateException.class);
  }

  @Test
  void googleRevokesToken() {
    server
        .expect(requestTo(SocialUnlinker.GOOGLE_REVOKE))
        .andExpect(method(HttpMethod.POST))
        .andExpect(content().formDataContains(java.util.Map.of("token", "google-user-token")))
        .andRespond(withSuccess());

    unlinker.unlink(SocialProvider.GOOGLE, "google-user-token");
    server.verify();
  }

  @Test
  void providerErrorIsFailure() {
    server
        .expect(requestTo(SocialUnlinker.KAKAO_UNLINK))
        .andRespond(withStatus(HttpStatus.UNAUTHORIZED));

    assertThatThrownBy(() -> unlinker.unlink(SocialProvider.KAKAO, "expired"))
        .isInstanceOf(RuntimeException.class);
  }
}
