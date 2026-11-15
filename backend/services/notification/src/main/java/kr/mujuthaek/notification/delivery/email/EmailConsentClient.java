package kr.mujuthaek.notification.delivery.email;

import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.notification.delivery.DeliveryException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

@Component
class EmailConsentClient {
  private final RestClient http;

  EmailConsentClient(
      @Value("${notification.mail.consent-api-url:http://localhost:8080}") String base,
      @Value("${notification.internal.token:}") String token) {
    var factory = new SimpleClientHttpRequestFactory();
    factory.setConnectTimeout(Duration.ofSeconds(3));
    factory.setReadTimeout(Duration.ofSeconds(3));
    http =
        RestClient.builder()
            .baseUrl(base)
            .requestFactory(factory)
            .defaultHeader("X-Notification-Token", token)
            .build();
  }

  record Consent(boolean allowed, String unsubscribeToken) {}

  Consent check(UUID userId, String email, String type) throws DeliveryException {
    try {
      Consent result =
          http.post()
              .uri("/internal/email-eligibility")
              .body(Map.of("userId", userId, "email", email, "type", type))
              .retrieve()
              .body(Consent.class);
      if (result == null) throw new DeliveryException("EMAIL_CONSENT_UNAVAILABLE", false);
      return result;
    } catch (RestClientException e) {
      throw new DeliveryException("EMAIL_CONSENT_UNAVAILABLE", false);
    }
  }
}
