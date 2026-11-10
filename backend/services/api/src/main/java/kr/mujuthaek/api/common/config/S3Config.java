package kr.mujuthaek.api.common.config;

import java.net.URI;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

/** S3 클라이언트. endpoint가 있으면 로컬 MinIO(경로 방식 주소, 고정 키), 없으면 AWS S3(기본 인증)예요. */
@Configuration
@EnableConfigurationProperties(S3Properties.class)
class S3Config {

  @Bean(destroyMethod = "close")
  S3Client s3Client(S3Properties props) {
    var builder = S3Client.builder().region(Region.of(props.region()));
    if (props.usesEndpoint()) {
      builder
          .endpointOverride(URI.create(props.endpoint()))
          .forcePathStyle(true)
          .credentialsProvider(
              StaticCredentialsProvider.create(
                  AwsBasicCredentials.create(props.accessKey(), props.secretKey())));
    }
    return builder.build();
  }
}
