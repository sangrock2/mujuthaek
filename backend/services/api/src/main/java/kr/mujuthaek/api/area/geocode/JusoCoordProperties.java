package kr.mujuthaek.api.area.geocode;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 도로명주소 좌표제공 API 설정. 키가 비면 부르지 않아요(사전에 없는 새 건물은 법정동 대표점으로).
 *
 * @param apiKey 승인키 (환경 변수 JUSO_COORD_API_KEY, 검색 API와 다른 키)
 * @param perSecond 초당 호출 수
 * @param perDay 하루 호출 수
 * @param retries 시스템 오류·연결 실패 때 다시 부를 횟수
 */
@ConfigurationProperties("mujuthaek.area.juso-coord")
public record JusoCoordProperties(
    String baseUrl, String apiKey, int perSecond, int perDay, int retries, Duration timeout) {

  public boolean hasKey() {
    return apiKey != null && !apiKey.isBlank();
  }
}
