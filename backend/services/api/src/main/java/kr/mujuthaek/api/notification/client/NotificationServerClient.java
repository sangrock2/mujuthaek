package kr.mujuthaek.api.notification.client;

import java.time.Duration;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import tools.jackson.databind.JsonNode;

/**
 * 알림 서버 내부 API({@code /internal/**}) 클라이언트. 관리자 「알림」 화면의 발송 결과(성공·실패·대기)를 이 서버를 거쳐 받아요. 알림 서버에 닿지
 * 못하면 빈 값이라 화면은 알림함 지표만 보여 줘요. 토큰·주소는 로그에 남기지 않아요.
 */
@Component
public class NotificationServerClient {

  private static final Logger log = LoggerFactory.getLogger(NotificationServerClient.class);

  private final RestClient http;

  @Autowired
  public NotificationServerClient(Properties properties) {
    this(properties, defaultBuilder(properties));
  }

  /** 요청 빌더를 받아요(시험에서 가짜 서버를 붙일 때). */
  public NotificationServerClient(Properties properties, RestClient.Builder builder) {
    builder.baseUrl(properties.baseUrl());
    if (properties.token() != null && !properties.token().isBlank()) {
      builder.defaultHeader(HttpHeaders.AUTHORIZATION, "Bearer " + properties.token());
    }
    this.http = builder.build();
  }

  /**
   * 최근 {@code days}일 발송 결과: {days, byType[{type, channel, sent, failed, pending}], failures[...]}
   */
  public Optional<JsonNode> deliveryStats(int days) {
    try {
      return Optional.ofNullable(
          http.get().uri("/internal/stats?days={days}", days).retrieve().body(JsonNode.class));
    } catch (RestClientException e) {
      log.warn("알림 서버 발송 통계를 받지 못했어요 ({})", e.getClass().getSimpleName());
      return Optional.empty();
    }
  }

  private static RestClient.Builder defaultBuilder(Properties properties) {
    var factory = new SimpleClientHttpRequestFactory();
    factory.setConnectTimeout(properties.timeout());
    factory.setReadTimeout(properties.timeout());
    return RestClient.builder().requestFactory(factory);
  }

  /**
   * 알림 서버 내부 API 설정.
   *
   * @param token 알림 서버와 같은 NOTIFICATION_INTERNAL_TOKEN. 비면 보내지 않아요(로컬은 같은 컴퓨터 요청만 받음)
   */
  @ConfigurationProperties("mujuthaek.notification.server")
  public record Properties(String baseUrl, String token, Duration timeout) {}

  @Configuration
  @EnableConfigurationProperties(Properties.class)
  static class Config {}
}
