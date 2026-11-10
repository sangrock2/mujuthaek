package kr.mujuthaek.api.notice.controller;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.time.Duration;
import java.util.UUID;
import kr.mujuthaek.api.notice.controller.spec.NoticeFileApiSpec;
import kr.mujuthaek.api.notice.service.internal.NoticeFileService;
import org.springframework.http.CacheControl;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 공고 원문 PDF (설명은 {@link NoticeFileApiSpec}). */
@RestController
@RequestMapping("/api/v1/notices")
class NoticeFileController implements NoticeFileApiSpec {

  /** 공개 공고 원문이라 공유 캐시도 돼요. 버전이 바뀌어 파일이 달라지면 해시(ETag)가 달라져 다시 받아요. */
  private static final CacheControl CACHE = CacheControl.maxAge(Duration.ofHours(1)).cachePublic();

  private final NoticeFileService files;

  NoticeFileController(NoticeFileService files) {
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
    PdfResponses.send(files, files.noticePdf(id, fileId), request, response, CACHE);
  }
}
