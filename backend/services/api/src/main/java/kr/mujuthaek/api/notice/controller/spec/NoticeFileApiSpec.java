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
    name = "공고 원문",
    description =
        "공고 원문 PDF를 이 서버가 내려줘요(수집할 때 우리 저장소에 둔 원본 그대로). 로그인 없이 누구나 불러요. "
            + "주소는 공고 상세의 files[].viewUrl이고, 화면은 근거의 fileId·page로 그 PDF의 그 쪽을 열어요.")
public interface NoticeFileApiSpec {

  @Operation(
      summary = "공고 원문 PDF",
      description =
          "지금 공개 버전의 첨부 PDF 하나를 application/pdf로 줘요(Content-Disposition inline). ETag는 파일 해시라 "
              + "If-None-Match가 같으면 304예요. 쪽 범위 요청(Range)은 받지 않고 늘 전체를 줘요. 상세의 files[].viewUrl이 null인 "
              + "문서(HWP·그림만·보관 기한 지남·이전 결과)는 이 API로 받을 수 없어 화면이 기관 사이트로 보내요.")
  @ApiResponse(
      responseCode = "200",
      description = "PDF 파일",
      content = @Content(mediaType = "application/pdf"))
  @ApiResponse(responseCode = "304", description = "ETag가 같아요(브라우저 캐시를 써요)")
  @ApiResponse(
      responseCode = "404",
      description =
          "NOTICE_NOT_FOUND — 공고가 없거나 숨김·공개 전이에요. NOTICE_FILE_NOT_FOUND — 그 문서가 없거나 PDF가 아니거나 "
              + "보류됐거나, 우리 저장소에 원본이 없어요(보관 기한이 지나 지움 등)")
  @ApiResponse(responseCode = "503", description = "NOTICE_FILE_UNAVAILABLE — 파일 저장소에 연결하지 못했어요")
  void file(
      @Parameter(description = "공고 ID") UUID id,
      @Parameter(description = "문서 ID (상세의 files[].id, 예: file-1)") String fileId,
      @Parameter(hidden = true) HttpServletRequest request,
      @Parameter(hidden = true) HttpServletResponse response)
      throws IOException;
}
