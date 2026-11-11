package kr.mujuthaek.api.notice.service.internal;

import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.notice.client.ExtractionReviewClient;
import kr.mujuthaek.api.notice.mapper.NoticeDetailMapper;
import kr.mujuthaek.api.notice.repository.NoticeFileStore;
import kr.mujuthaek.api.notice.repository.NoticeFileStore.NoticeFileStoreException;
import kr.mujuthaek.api.notice.repository.NoticeFileStore.StoredFile;
import kr.mujuthaek.api.notice.repository.NoticeQueries;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * 공고 원문 PDF 내려주기. 수집기가 S3에 둔 원본을 그대로 스트림으로 넘겨요(공개 공고 원문이라 사용자 정보 없음).
 *
 * <ul>
 *   <li>공개 공고: 지금 공개 버전의 추출 결과에서 그 문서의 S3 위치(sourceFiles)를 찾아요. 숨김·공개 전 공고, PDF가 아닌 문서, 보류한 문서, 위치가
 *       없는 이전 결과는 404예요.
 *   <li>관리자 검수: 작업 ID로 추출 서비스에 작업 원본의 첨부 위치를 물어요(검수 대기처럼 아직 공개 전인 결과도 봐야 해서요).
 * </ul>
 */
@Service
public class NoticeFileService {

  private final NoticeQueries queries;
  private final NoticeFileStore files;
  private final ExtractionReviewClient reviews;
  private final JsonMapper json;

  public NoticeFileService(
      NoticeQueries queries,
      NoticeFileStore files,
      ExtractionReviewClient reviews,
      JsonMapper json) {
    this.queries = queries;
    this.files = files;
    this.reviews = reviews;
    this.json = json;
  }

  /**
   * 내려줄 PDF 하나.
   *
   * @param etag 문서 해시 (같으면 브라우저 캐시를 써요). 모르면 null
   */
  public record PdfFile(String name, String etag, String s3Key) {}

  /** 공개 공고의 원문 PDF. 없으면 404 (공고가 없으면 NOTICE_NOT_FOUND, 파일이 없으면 NOTICE_FILE_NOT_FOUND). */
  public PdfFile noticePdf(UUID noticeId, String fileId) {
    var current =
        queries
            .current(noticeId)
            .orElseThrow(() -> new CustomException(ErrorCode.NOTICE_NOT_FOUND));
    var pdf = NoticeDetailMapper.sourcePdfs(json.readTree(current.payload())).get(fileId);
    if (pdf == null) {
      throw new CustomException(ErrorCode.NOTICE_FILE_NOT_FOUND);
    }
    return new PdfFile(pdf.name(), hash(pdf.sha256()), pdf.s3Key());
  }

  /** 관리자 검수 작업의 원문 PDF (작업 원본 첨부 중 PDF만). 작업이 없으면 NOTICE_REVIEW_NOT_FOUND. */
  public PdfFile reviewPdf(String jobId, String fileId) {
    JsonNode body = reviews.files(jobId);
    if (body == null || body.isNull()) {
      throw new CustomException(ErrorCode.NOTICE_REVIEW_NOT_FOUND);
    }
    for (JsonNode f : body.path("files")) {
      String key = f.path("s3Key").asString(null);
      if (fileId.equals(f.path("documentId").asString(null))
          && "pdf".equals(f.path("fileType").asString(null))
          && NoticeFileStore.allowed(key)) {
        return new PdfFile(
            f.path("name").asString(null), hash(f.path("sha256").asString(null)), key);
      }
    }
    throw new CustomException(ErrorCode.NOTICE_FILE_NOT_FOUND);
  }

  /** 파일을 열어요. 다 읽은 뒤 닫아야 해요. 저장소에 없으면(보관 기한 지남) 404, 연결하지 못하면 503. */
  public StoredFile open(PdfFile file) {
    Optional<StoredFile> found;
    try {
      found = files.open(file.s3Key());
    } catch (NoticeFileStoreException e) {
      throw new CustomException(ErrorCode.NOTICE_FILE_UNAVAILABLE);
    }
    return found.orElseThrow(() -> new CustomException(ErrorCode.NOTICE_FILE_NOT_FOUND));
  }

  /** 해시는 64자리 16진수일 때만 ETag로 써요. */
  private static String hash(String sha256) {
    return sha256 != null && sha256.matches("[0-9a-f]{64}") ? sha256 : null;
  }
}
