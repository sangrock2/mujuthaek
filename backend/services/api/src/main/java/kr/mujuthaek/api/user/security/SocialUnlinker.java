package kr.mujuthaek.api.user.security;

import kr.mujuthaek.api.user.domain.SocialProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.client.RestClient;

/**
 * 탈퇴할 때 소셜 제공자 쪽 연결(우리 앱에 대한 동의)을 끊어요. 탈퇴 직전 재인증으로 받은 그 사용자의 access token을 써서, 제공자 토큰을 저장하지도 강한 권한의
 * Admin 키를 두지도 않아요.
 *
 * <ul>
 *   <li>카카오: POST https://kapi.kakao.com/v1/user/unlink (Authorization: Bearer 사용자 토큰)
 *   <li>네이버: POST https://nid.naver.com/oauth2.0/token grant_type=delete, client_id, client_secret,
 *       access_token, service_provider=NAVER
 *   <li>구글: POST https://oauth2.googleapis.com/revoke token=사용자 토큰
 * </ul>
 */
@Component
class SocialUnlinker {

  static final String KAKAO_UNLINK = "https://kapi.kakao.com/v1/user/unlink";
  static final String NAVER_TOKEN = "https://nid.naver.com/oauth2.0/token";
  static final String GOOGLE_REVOKE = "https://oauth2.googleapis.com/revoke";

  private final RestClient http;
  private final ClientRegistrationRepository registrations;

  @Autowired
  SocialUnlinker(ClientRegistrationRepository registrations) {
    this(RestClient.builder(), registrations);
  }

  /** 테스트에서 가짜 서버(MockRestServiceServer)를 끼울 수 있게 builder를 받아요. */
  SocialUnlinker(RestClient.Builder builder, ClientRegistrationRepository registrations) {
    this.http = builder.build();
    this.registrations = registrations;
  }

  /** 실패하면 예외 (제공자 오류 응답, 연결 실패). 호출하는 쪽에서 로그만 남기고 탈퇴는 이어가요. */
  void unlink(SocialProvider provider, String accessToken) {
    switch (provider) {
      case KAKAO ->
          http.post()
              .uri(KAKAO_UNLINK)
              .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken)
              .retrieve()
              .toBodilessEntity();
      case NAVER -> {
        ClientRegistration naver = registrations.findByRegistrationId("naver");
        var form = new LinkedMultiValueMap<String, String>();
        form.add("grant_type", "delete");
        form.add("client_id", naver.getClientId());
        form.add("client_secret", naver.getClientSecret());
        form.add("access_token", accessToken);
        form.add("service_provider", "NAVER");
        String body =
            http.post()
                .uri(NAVER_TOKEN)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(form)
                .retrieve()
                .body(String.class);
        if (body == null || !body.contains("\"success\"")) { // 네이버는 실패해도 200에 {"error": …}로 와요
          throw new IllegalStateException("네이버 연결 끊기 실패: " + body);
        }
      }
      case GOOGLE -> {
        var form = new LinkedMultiValueMap<String, String>();
        form.add("token", accessToken);
        http.post()
            .uri(GOOGLE_REVOKE)
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(form)
            .retrieve()
            .toBodilessEntity();
      }
    }
  }
}
