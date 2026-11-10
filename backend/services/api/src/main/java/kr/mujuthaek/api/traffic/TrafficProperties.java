package kr.mujuthaek.api.traffic;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 트래픽 설정.
 *
 * @param ipSalt IP 해시에 섞는 비밀 값(TRAFFIC_IP_SALT). 날짜와 함께 섞어 날마다 해시가 달라져요(오래 따라가지 못하게)
 * @param rawIpDays 원본 IP 보관 일수. 지나면 지워요(보안 대응용)
 * @param keepDays 요청 기록 보관 일수
 * @param ingestToken 프론트 서버가 화면 요청을 넘길 때 쓰는 비밀 값(TRAFFIC_INGEST_TOKEN). 비면 화면 요청을 받지 않아요
 * @param ga GA4 Data API 설정
 */
@ConfigurationProperties("mujuthaek.traffic")
public record TrafficProperties(
    String ipSalt, int rawIpDays, int keepDays, String ingestToken, Ga ga) {

  public boolean ingestEnabled() {
    return ingestToken != null && !ingestToken.isBlank();
  }

  /**
   * @param propertyId GA4 속성 ID(숫자). 비면 GA 숫자를 가져오지 않아요(화면에 「GA 연결 안 됨」)
   * @param credentialsFile 서비스 계정 키(JSON) 파일 경로. 저장소 밖에 두고 경로만 줘요
   * @param cacheTtl 같은 보고서를 다시 묻지 않는 시간(GA 호출 한도)
   * @param timeout 연결·응답 기다리는 시간
   */
  public record Ga(String propertyId, String credentialsFile, Duration cacheTtl, Duration timeout) {

    public boolean configured() {
      return propertyId != null
          && !propertyId.isBlank()
          && credentialsFile != null
          && !credentialsFile.isBlank();
    }
  }
}
