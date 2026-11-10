package kr.mujuthaek.api.area.geocode;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 도로명주소 검색 API(행정안전부 도로명주소 개발자센터) 설정.
 *
 * @param apiKey 승인키. 환경 변수 JUSO_SEARCH_API_KEY로만 받아요. 비어 있으면 API를 부르지 않아요
 * @param perSecond 초당 호출 수. 넘으면 다음 1초 칸까지 기다려요
 * @param perDay 하루(한국 시각) 호출 수. 넘으면 그날은 부르지 않고 RATE_LIMITED
 * @param retries 시스템 오류·연결 실패 때 다시 부르는 횟수
 */
@ConfigurationProperties("mujuthaek.area.juso-search")
public record JusoSearchProperties(
    String baseUrl, String apiKey, int perSecond, int perDay, int retries, Duration timeout) {

  public boolean hasKey() {
    return apiKey != null && !apiKey.isBlank();
  }
}
