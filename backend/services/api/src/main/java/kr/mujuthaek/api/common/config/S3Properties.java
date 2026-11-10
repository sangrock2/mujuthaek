package kr.mujuthaek.api.common.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 원본 파일 저장소(S3) 설정. collector와 같은 환경 변수(S3_ENDPOINT, S3_BUCKET)를 써요.
 *
 * @param endpoint 로컬 MinIO 주소. 비우면 AWS S3를 써요(인증은 EC2 역할 등 기본 방식)
 * @param accessKey endpoint가 있을 때만 쓰는 키 (로컬 MinIO 계정)
 */
@ConfigurationProperties("mujuthaek.s3")
public record S3Properties(
    String endpoint, String bucket, String region, String accessKey, String secretKey) {

  public boolean usesEndpoint() {
    return endpoint != null && !endpoint.isBlank();
  }
}
