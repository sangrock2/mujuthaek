package kr.mujuthaek.api.common.config;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import org.junit.jupiter.api.Test;

class S3ConfigTest {

  @Test
  void endpointMeansLocalMinio() {
    var props =
        new S3Properties("http://localhost:9000", "mujuthaek-raw", "ap-northeast-2", "minio", "x");
    try (var s3 = new S3Config().s3Client(props)) {
      assertThat(s3.serviceClientConfiguration().endpointOverride())
          .contains(URI.create("http://localhost:9000"));
    }
  }

  @Test
  void blankEndpointMeansAwsS3() {
    var props = new S3Properties("", "mujuthaek-raw", "ap-northeast-2", null, null);
    assertThat(props.usesEndpoint()).isFalse();
    try (var s3 = new S3Config().s3Client(props)) {
      assertThat(s3.serviceClientConfiguration().endpointOverride()).isEmpty();
    }
  }
}
