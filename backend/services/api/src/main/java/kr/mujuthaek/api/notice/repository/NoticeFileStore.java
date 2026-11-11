package kr.mujuthaek.api.notice.repository;

import java.io.InputStream;
import java.util.Optional;

/**
 * 수집기가 S3에 둔 공고 원문 첨부(raw/ 경로)를 읽어요. api는 raw/에 읽기만 해요. 시험에서는 가짜로 바꿔 끼워요.
 *
 * <p>raw/ 밖의 경로나 「..」가 든 경로는 읽지 않아요(다른 파일을 내려주지 않게).
 */
public interface NoticeFileStore {

  String PREFIX = "raw/";

  /**
   * 파일 하나를 스트림으로 열어요. 다 읽은 뒤 닫아야 해요. 없으면(보관 기한이 지나 지웠거나 경로가 틀림) 빈 값이에요.
   *
   * @throws IllegalArgumentException raw/ 밖의 경로
   * @throws NoticeFileStoreException 저장소에 연결하지 못함
   */
  Optional<StoredFile> open(String key);

  /** 연 파일. length는 모르면 null이에요. */
  record StoredFile(InputStream body, Long length) {}

  /** 저장소에 연결하지 못했어요(일시 오류). */
  class NoticeFileStoreException extends RuntimeException {
    public NoticeFileStoreException(String message, Throwable cause) {
      super(message, cause);
    }
  }

  static boolean allowed(String key) {
    return key != null && key.startsWith(PREFIX) && !key.contains("..") && !key.contains("\\");
  }
}
