package kr.mujuthaek.api.notice.controller;

import static java.nio.charset.StandardCharsets.UTF_8;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.io.InputStream;
import kr.mujuthaek.api.notice.repository.NoticeFileStore.StoredFile;
import kr.mujuthaek.api.notice.service.internal.NoticeFileService;
import kr.mujuthaek.api.notice.service.internal.NoticeFileService.PdfFile;
import org.springframework.http.CacheControl;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.context.request.ServletWebRequest;

/**
 * 원문 PDF 응답: S3 스트림을 그대로 흘려보내요(파일 전체를 메모리에 올리지 않음). 쪽 범위 요청(Range)은 받지 않고 늘 전체를 줘요. 문서 해시를 ETag로 줘서
 * 같은 파일이면 304로 끝내요(S3를 다시 읽지 않음). 파일을 찾지 못하면 쓰기 전에 오류가 나서 보통의 오류 응답(JSON)이 나가요.
 */
final class PdfResponses {

  private PdfResponses() {}

  static void send(
      NoticeFileService files,
      PdfFile file,
      HttpServletRequest request,
      HttpServletResponse response,
      CacheControl cache)
      throws IOException {
    String etag = file.etag() == null ? null : '"' + file.etag() + '"';
    if (etag != null && new ServletWebRequest(request, response).checkNotModified(etag)) {
      response.setHeader(HttpHeaders.CACHE_CONTROL, cache.getHeaderValue());
      return;
    }
    StoredFile stored = files.open(file);
    try (InputStream in = stored.body()) {
      response.setContentType(MediaType.APPLICATION_PDF_VALUE);
      response.setHeader(
          HttpHeaders.CONTENT_DISPOSITION,
          ContentDisposition.inline().filename(name(file), UTF_8).build().toString());
      response.setHeader(HttpHeaders.CACHE_CONTROL, cache.getHeaderValue());
      if (etag != null) {
        response.setHeader(HttpHeaders.ETAG, etag);
      }
      if (stored.length() != null && stored.length() >= 0) {
        response.setContentLengthLong(stored.length());
      }
      in.transferTo(response.getOutputStream());
    }
  }

  private static String name(PdfFile file) {
    String name = file.name() == null ? "" : file.name().strip();
    return name.isEmpty() ? "notice.pdf" : name;
  }
}
