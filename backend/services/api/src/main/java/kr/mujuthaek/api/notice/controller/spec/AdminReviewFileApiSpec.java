package kr.mujuthaek.api.notice.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;

@Tag(
    name = "관리자 공고 원문",
    description =
        "검수 작업(추출 작업)의 원문 PDF를 이 서버가 내려줘요. 「추출 과정 보기」에서 근거 id를 누르면 그 PDF의 그 쪽을 열어요. "
            + "아직 공개 전인 검수 대기 결과도 볼 수 있게 추출 서비스에 작업 원본의 첨부 위치를 물어요. "
            + "권한 NOTICE_REVIEW가 있는 관리자만 불러요.")
public interface AdminReviewFileApiSpec {

  @Operation(
      summary = "검수 작업의 원문 PDF",
      description =
          "작업 원본의 첨부 중 PDF 하나를 application/pdf로 줘요. 문서 ID는 추출 과정의 documents[].id(file-1 …)와 같아요. "
              + "ETag는 파일 해시라 If-None-Match가 같으면 304예요. 공개 공고 원문이라 사용자 정보는 없어요.")
  @ApiResponse(
      responseCode = "200",
      description = "PDF 파일",
      content = @Content(mediaType = "application/pdf"))
  @ApiResponse(responseCode = "304", description = "ETag가 같아요(브라우저 캐시를 써요)")
  @ApiResponse(
      responseCode = "404",
      description =
          "NOTICE_REVIEW_NOT_FOUND — 없는 작업이에요. NOTICE_FILE_NOT_FOUND — 그 문서가 없거나 PDF가 아니거나 "
              + "우리 저장소에 원본이 없어요")
  @ApiResponse(
      responseCode = "503",
      description =
          "NOTICE_REVIEW_UNAVAILABLE — 검수 서버에 연결하지 못했어요. NOTICE_FILE_UNAVAILABLE — 파일 저장소에 연결하지 못했어요")
  void file(
      @Parameter(description = "추출 작업 ID(검수 작업 ID와 같아요)") UUID id,
      @Parameter(description = "문서 ID (추출 과정의 documents[].id, 예: file-1)") String fileId,
      @Parameter(hidden = true) HttpServletRequest request,
      @Parameter(hidden = true) HttpServletResponse response)
      throws IOException;
}
