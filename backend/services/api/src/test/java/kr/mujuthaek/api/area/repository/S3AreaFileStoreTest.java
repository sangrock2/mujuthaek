package kr.mujuthaek.api.area.repository;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import kr.mujuthaek.api.common.config.S3Properties;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;

class S3AreaFileStoreTest {

  private final S3Client s3 = mock(S3Client.class);
  private final S3AreaFileStore store =
      new S3AreaFileStore(
          s3, new S3Properties(null, "mujuthaek-raw", "ap-northeast-2", null, null));

  @Test
  void readsAreaKeysFromTheConfiguredBucket() {
    store.open("area/BUS_STOP/2025-10-31/bus_stop.csv");

    var request = ArgumentCaptor.forClass(GetObjectRequest.class);
    verify(s3).getObject(request.capture());
    assertThat(request.getValue().bucket()).isEqualTo("mujuthaek-raw");
    assertThat(request.getValue().key()).isEqualTo("area/BUS_STOP/2025-10-31/bus_stop.csv");
  }

  @Test
  void refusesKeysOutsideArea() {
    for (String key : new String[] {"raw/lh/1/v1/00-공고.pdf", "area/../raw/x.pdf", null}) {
      assertThatThrownBy(() -> store.open(key)).isInstanceOf(IllegalArgumentException.class);
    }
    verify(s3, never()).getObject(any(GetObjectRequest.class));
  }
}
