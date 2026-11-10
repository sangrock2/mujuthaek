package kr.mujuthaek.api.notice.client;

import java.util.function.Supplier;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.client.BufferingClientHttpRequestFactory;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import tools.jackson.databind.JsonNode;

/**
 * 수집기 관리자 API(:8093, collector admin_api.py) 클라이언트. 관리자 「수집 현황」 화면이 이 서버를 거쳐 불러요. 응답은 수집기 JSON
 * 그대로예요.
 *
 * <p>404(없는 출처)는 {@link ErrorCode#NOT_FOUND}, 연결 실패·인증 실패·5xx는 {@link
 * ErrorCode#NOTICE_COLLECTOR_UNAVAILABLE}. 토큰·주소는 로그에 남기지 않아요.
 */
@Component
public class CollectorAdminClient {

  private static final Logger log = LoggerFactory.getLogger(CollectorAdminClient.class);

  private final RestClient http;

  @Autowired
  public CollectorAdminClient(Properties properties) {
    this(properties, defaultBuilder(properties));
  }

  /** 요청 빌더를 받아요(시험에서 가짜 서버를 붙일 때). */
  public CollectorAdminClient(Properties properties, RestClient.Builder builder) {
    builder.baseUrl(properties.baseUrl());
    if (properties.token() != null && !properties.token().isBlank()) {
      builder.defaultHeader(HttpHeaders.AUTHORIZATION, "Bearer " + properties.token());
    }
    this.http = builder.build();
  }

  /** 출처별 상태: {asOf, summary{ok, late, fail, paused}, sources[...]} */
  public JsonNode sources() {
    return call(() -> http.get().uri("/sources").retrieve().body(JsonNode.class));
  }

  /** 멈춤(enabled=false) 또는 다시 켜기. */
  public JsonNode setEnabled(String code, boolean enabled) {
    return call(
        () ->
            http.post()
                .uri("/sources/{code}/{action}", code, enabled ? "resume" : "pause")
                .retrieve()
                .body(JsonNode.class));
  }

  /** 지금 한 번 수집 (수집기가 뒤에서 돌려요). 다른 수집 중·멈춤·이미 수집 중이면 {@link ErrorCode#CONFLICT}. */
  public JsonNode runNow(String code) {
    return call(() -> http.post().uri("/sources/{code}/run", code).retrieve().body(JsonNode.class));
  }

  private JsonNode call(Supplier<JsonNode> request) {
    try {
      return request.get();
    } catch (RestClientResponseException e) {
      if (e.getStatusCode().value() == 404) {
        throw new CustomException(ErrorCode.NOT_FOUND, "없는 수집 출처예요");
      }
      if (e.getStatusCode().value() == 409) {
        throw new CustomException(ErrorCode.CONFLICT, upstreamError(e));
      }
      log.warn("수집기 관리자 API가 오류로 답했어요 (status {})", e.getStatusCode().value());
      throw new CustomException(ErrorCode.NOTICE_COLLECTOR_UNAVAILABLE);
    } catch (RestClientException e) {
      log.warn("수집기 관리자 API에 연결하지 못했어요 ({})", e.getClass().getSimpleName());
      throw new CustomException(ErrorCode.NOTICE_COLLECTOR_UNAVAILABLE);
    }
  }

  /** 수집기 오류 본문의 error(한국어 설명). */
  private static String upstreamError(RestClientResponseException e) {
    try {
      JsonNode body = e.getResponseBodyAs(JsonNode.class);
      JsonNode error = body == null ? null : body.get("error");
      return error != null && error.isString() ? error.asString() : null;
    } catch (RuntimeException ignored) {
      return null;
    }
  }

  private static RestClient.Builder defaultBuilder(Properties properties) {
    var factory = new SimpleClientHttpRequestFactory();
    factory.setConnectTimeout(properties.timeout());
    factory.setReadTimeout(properties.timeout());
    // 본문을 모아 Content-Length를 붙여 보내요. 조각 전송(chunked)이면 파이썬 http.server가 본문을 빈 것으로 읽어 승인·반려·다시 열기가
    // 400이 됐어요(2026-10-25 로컬 실제 흐름에서 발견, 가짜 서버 시험으로는 안 보임)
    return RestClient.builder().requestFactory(new BufferingClientHttpRequestFactory(factory));
  }

  /**
   * 수집기 관리자 API 설정.
   *
   * @param token 수집기와 같은 COLLECTOR_ADMIN_TOKEN. 비면 보내지 않아요(로컬은 같은 컴퓨터 요청만 받음)
   */
  @ConfigurationProperties("mujuthaek.notice.collector-admin")
  public record Properties(String baseUrl, String token, java.time.Duration timeout) {}

  @Configuration
  @EnableConfigurationProperties(Properties.class)
  static class Config {}
}
