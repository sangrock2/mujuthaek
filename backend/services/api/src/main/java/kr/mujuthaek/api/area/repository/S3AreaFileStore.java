package kr.mujuthaek.api.area.repository;

import java.io.InputStream;
import kr.mujuthaek.api.common.config.S3Properties;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;

/** area/ 경로의 원천 파일을 S3에서 스트림으로 읽어요. 파일 전체를 메모리에 올리지 않아요. api는 area/에 읽기만 해요. */
@Component
public class S3AreaFileStore {

  static final String PREFIX = "area/";

  private final S3Client s3;
  private final String bucket;

  public S3AreaFileStore(S3Client s3, S3Properties props) {
    this.s3 = s3;
    this.bucket = props.bucket();
  }

  /** 다 읽은 뒤 닫아야 해요 (S3 연결을 돌려줘요). */
  public InputStream open(String key) {
    if (key == null || !key.startsWith(PREFIX) || key.contains("..")) {
      throw new IllegalArgumentException("area/ 경로의 파일만 읽어요: " + key);
    }
    return s3.getObject(GetObjectRequest.builder().bucket(bucket).key(key).build());
  }
}
