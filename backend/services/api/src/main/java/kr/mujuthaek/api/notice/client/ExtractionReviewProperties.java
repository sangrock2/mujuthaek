package kr.mujuthaek.api.notice.client;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 추출 서비스 검수 API(:8092) 설정. 관리자 화면은 이 api 서버만 부르고, 이 서버가 검수 API를 대신 불러요.
 *
 * @param baseUrl 검수 API 주소. 예: http://extraction:8092
 * @param token 검수 API 토큰(EXTRACTION_REVIEW_TOKEN). 비면 Authorization을 보내지 않아요(같은 컴퓨터에서만 받는 로컬 개발용)
 * @param timeout 연결·응답 기다리는 시간
 */
@ConfigurationProperties("mujuthaek.notice.extraction-review")
public record ExtractionReviewProperties(String baseUrl, String token, Duration timeout) {

  public boolean hasToken() {
    return token != null && !token.isBlank();
  }
}
