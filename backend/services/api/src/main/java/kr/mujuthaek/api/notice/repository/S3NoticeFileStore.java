package kr.mujuthaek.api.notice.repository;

import java.util.Optional;
import kr.mujuthaek.api.common.config.S3Properties;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.core.exception.SdkException;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.S3Exception;

/** 공고 원문 첨부를 S3(로컬 MinIO)에서 스트림으로 읽어요. 파일 전체를 메모리에 올리지 않아요. */
@Component
class S3NoticeFileStore implements NoticeFileStore {

  private final S3Client s3;
  private final String bucket;

  S3NoticeFileStore(S3Client s3, S3Properties props) {
    this.s3 = s3;
    this.bucket = props.bucket();
  }

  @Override
  public Optional<StoredFile> open(String key) {
    if (!NoticeFileStore.allowed(key)) {
      throw new IllegalArgumentException("raw/ 경로의 파일만 읽어요");
    }
    try {
      ResponseInputStream<GetObjectResponse> in =
          s3.getObject(GetObjectRequest.builder().bucket(bucket).key(key).build());
      return Optional.of(new StoredFile(in, in.response().contentLength()));
    } catch (S3Exception e) {
      if (e.statusCode() == 404) { // NoSuchKey: 보관 기한이 지나 지웠거나 경로가 틀림
        return Optional.empty();
      }
      throw new NoticeFileStoreException("원문 파일 저장소가 오류로 답했어요", e);
    } catch (SdkException e) {
      throw new NoticeFileStoreException("원문 파일 저장소에 연결하지 못했어요", e);
    }
  }
}
