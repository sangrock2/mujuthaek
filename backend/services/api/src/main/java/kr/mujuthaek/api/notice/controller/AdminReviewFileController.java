package kr.mujuthaek.api.notice.controller;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.time.Duration;
import java.util.UUID;
import kr.mujuthaek.api.notice.controller.spec.AdminReviewFileApiSpec;
import kr.mujuthaek.api.notice.service.internal.NoticeFileService;
import org.springframework.http.CacheControl;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 관리자 검수 작업의 원문 PDF (설명은 {@link AdminReviewFileApiSpec}). 권한은 /api/admin/reviews/** 규칙(공고 검수 권한)을
 * 따라요.
 */
@RestController
@RequestMapping("/api/admin/reviews")
class AdminReviewFileController implements AdminReviewFileApiSpec {

  /** 로그인한 관리자에게만 주는 응답이라 공유 캐시에 두지 않아요. */
  private static final CacheControl CACHE =
      CacheControl.maxAge(Duration.ofMinutes(10)).cachePrivate();

  private final NoticeFileService files;

  AdminReviewFileController(NoticeFileService files) {
    this.files = files;
  }

  @Override
  @GetMapping("/{id}/files/{fileId}")
  public void file(
      @PathVariable UUID id,
      @PathVariable String fileId,
      HttpServletRequest request,
      HttpServletResponse response)
      throws IOException {
    PdfResponses.send(files, files.reviewPdf(id.toString(), fileId), request, response, CACHE);
  }
}
