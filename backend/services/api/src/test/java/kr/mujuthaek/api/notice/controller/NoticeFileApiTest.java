package kr.mujuthaek.api.notice.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;
import kr.mujuthaek.api.notice.NoticeApiFixture;
import kr.mujuthaek.api.notice.NoticeFixtures;
import kr.mujuthaek.api.notice.client.ExtractionReviewClient;
import kr.mujuthaek.api.notice.repository.NoticeFileStore;
import kr.mujuthaek.api.notice.repository.NoticeQueries;
import kr.mujuthaek.api.notice.service.internal.NoticeFileService;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.node.ObjectNode;

/** 공고 원문 PDF 내려주기 (공개 공고 · 관리자 검수 작업). S3는 가짜 저장소로 바꿔 끼워요. */
class NoticeFileApiTest {

  private static final String SHA = "b".repeat(64);
  private static final String KEY = "raw/lh/notice-1/v1/00-공고문.pdf";
  private static final byte[] PDF = "%PDF-1.4 가짜 원문".getBytes(StandardCharsets.UTF_8);

  private final NoticeApiFixture f = new NoticeApiFixture();
  private final Map<String, byte[]> stored = new HashMap<>(Map.of(KEY, PDF));
  private final AtomicInteger opened = new AtomicInteger();
  private boolean storeDown;
  private final NoticeFileStore store =
      key -> {
        if (storeDown) {
          throw new NoticeFileStore.NoticeFileStoreException("down", null);
        }
        opened.incrementAndGet();
        byte[] bytes = stored.get(key);
        return bytes == null
            ? Optional.empty()
            : Optional.of(
                new NoticeFileStore.StoredFile(
                    new ByteArrayInputStream(bytes), (long) bytes.length));
      };
  private final ExtractionReviewClient reviews = mock(ExtractionReviewClient.class);
  private final NoticeFileService service =
      new NoticeFileService(new NoticeQueries(f.jdbc), store, reviews, NoticeFixtures.JSON);
  private final MockMvc mvc =
      f.mvc(new NoticeFileController(service), new AdminReviewFileController(service));

  /** 공고문 PDF(file-1)와 그 S3 위치를 실은 공고. */
  private UUID noticeWithPdf() {
    return f.notice(
        p -> {
          ObjectNode d = p.get("notice").withArray("documents").addObject();
          d.put("id", "file-1")
              .put("kind", "PDF")
              .put("name", "공고문.pdf")
              .put("sha256", SHA)
              .put("originalUrl", "https://example.org/a.pdf")
              .put("pageCount", 3);
          p.withArray("sourceFiles").addObject().put("documentId", "file-1").put("s3Key", KEY);
        });
  }

  @Test
  void 상세의_viewUrl로_원문_PDF를_받고_같은_해시면_304() throws Exception {
    UUID id = noticeWithPdf();
    String viewUrl = f.queries.detail(id).files().get(1).viewUrl();
    assertThat(viewUrl).isEqualTo("/api/v1/notices/" + id + "/files/file-1");

    mvc.perform(get(viewUrl))
        .andExpect(status().isOk())
        .andExpect(content().contentType("application/pdf"))
        .andExpect(content().bytes(PDF))
        .andExpect(header().string("ETag", "\"" + SHA + "\""))
        .andExpect(header().string("Cache-Control", "max-age=3600, public"))
        .andExpect(
            header()
                .string(
                    "Content-Disposition", org.hamcrest.Matchers.startsWith("inline; filename=")));

    int before = opened.get();
    mvc.perform(get(viewUrl).header("If-None-Match", "\"" + SHA + "\""))
        .andExpect(status().isNotModified());
    assertThat(opened.get()).as("304면 저장소를 다시 읽지 않아요").isEqualTo(before);
  }

  @Test
  void PDF가_아니거나_위치가_없거나_공고가_없으면_404_저장소가_안되면_503() throws Exception {
    UUID id = noticeWithPdf();
    for (String file : new String[] {"text1", "file-9"}) {
      mvc.perform(get("/api/v1/notices/{id}/files/{file}", id, file))
          .andExpect(status().isNotFound())
          .andExpect(jsonPath("$.code").value("NOTICE_FILE_NOT_FOUND"));
    }
    mvc.perform(get("/api/v1/notices/{id}/files/file-1", UUID.randomUUID()))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOTICE_NOT_FOUND"));

    stored.clear(); // 보관 기한이 지나 지운 원본
    mvc.perform(get("/api/v1/notices/{id}/files/file-1", id))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOTICE_FILE_NOT_FOUND"));

    storeDown = true;
    mvc.perform(get("/api/v1/notices/{id}/files/file-1", id))
        .andExpect(status().isServiceUnavailable())
        .andExpect(jsonPath("$.code").value("NOTICE_FILE_UNAVAILABLE"));
  }

  @Test
  void 위치가_없는_이전_결과는_viewUrl이_없다() {
    UUID id = f.notice(p -> {});
    assertThat(f.queries.detail(id).files())
        .allSatisfy(file -> assertThat(file.viewUrl()).isNull());
  }

  @Test
  void 관리자는_검수_작업_원본의_PDF를_받는다() throws Exception {
    UUID job = UUID.randomUUID();
    ObjectNode body = NoticeFixtures.JSON.createObjectNode();
    var files = body.putArray("files");
    files
        .addObject()
        .put("documentId", "file-1")
        .put("name", "공고문.pdf")
        .put("fileType", "pdf")
        .put("s3Key", KEY)
        .put("sha256", SHA);
    files
        .addObject()
        .put("documentId", "file-2")
        .put("name", "공고문.hwp")
        .put("fileType", "hwp")
        .put("s3Key", "raw/lh/notice-1/v1/01-공고문.hwp")
        .put("sha256", SHA);
    files
        .addObject()
        .put("documentId", "file-3")
        .put("name", "이상.pdf")
        .put("fileType", "pdf")
        .put("s3Key", "area/x.pdf")
        .put("sha256", SHA);
    when(reviews.files(job.toString())).thenReturn(body);

    mvc.perform(get("/api/admin/reviews/{id}/files/file-1", job))
        .andExpect(status().isOk())
        .andExpect(content().contentType("application/pdf"))
        .andExpect(content().bytes(PDF))
        .andExpect(header().string("Cache-Control", "max-age=600, private"));
    for (String file : new String[] {"file-2", "file-3", "file-9"}) {
      mvc.perform(get("/api/admin/reviews/{id}/files/{file}", job, file))
          .andExpect(status().isNotFound())
          .andExpect(jsonPath("$.code").value("NOTICE_FILE_NOT_FOUND"));
    }
  }
}
