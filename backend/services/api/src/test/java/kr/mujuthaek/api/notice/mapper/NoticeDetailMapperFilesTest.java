package kr.mujuthaek.api.notice.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import java.util.function.Consumer;
import kr.mujuthaek.api.notice.NoticeFixtures;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.Evidence;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.FileLink;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.Header;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.node.ObjectNode;

/** 공고 원문 PDF 보기 (2026-11-11): 첨부의 앱 안 PDF 경로(viewUrl)와 근거가 어느 PDF의 쪽인지(fileId). */
class NoticeDetailMapperFilesTest {

  private static final UUID ID = UUID.fromString("00000000-0000-0000-0000-0000000000aa");
  private static final String SHA = "a".repeat(64);

  private static NoticeDetailResponse map(Consumer<ObjectNode> change) {
    ObjectNode p = NoticeFixtures.payload(UUID.randomUUID(), 1);
    change.accept(p);
    Header header =
        new Header(
            ID,
            "HOUSING",
            "t",
            null,
            null,
            null,
            "APPLYING",
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            false);
    return NoticeDetailMapper.map(
        header,
        p,
        List.of(),
        List.of(),
        1,
        false,
        OffsetDateTime.parse("2026-10-22T09:00:00+09:00"),
        LocalDate.of(2026, 10, 22));
  }

  private static void pdf(ObjectNode p, String id, Integer pageCount, String url) {
    ObjectNode d = p.get("notice").withArray("documents").addObject();
    d.put("id", id).put("kind", "PDF").put("name", id + ".pdf").put("sha256", SHA);
    if (url == null) {
      d.putNull("originalUrl");
    } else {
      d.put("originalUrl", url);
    }
    if (pageCount == null) {
      d.putNull("pageCount");
    } else {
      d.put("pageCount", pageCount);
    }
  }

  private static void located(ObjectNode p, String id, String key) {
    p.withArray("sourceFiles").addObject().put("documentId", id).put("s3Key", key);
  }

  /** 첫 근거를 PDF 글자의 글자 범위 근거(쪽 page, 그 PDF pageDocumentId)로 바꿔요. */
  private static void evidenceOn(ObjectNode p, Integer page, String pageDocumentId) {
    ObjectNode text = p.get("notice").withArray("documents").addObject();
    text.put("id", "pdf-text").put("kind", "TEXT").put("name", "첨부 PDF에서 읽은 글자");
    ObjectNode e = (ObjectNode) p.get("notice").get("evidence").get(0);
    e.put("sourceId", "pdf-text");
    ObjectNode locator = (ObjectNode) e.get("locator");
    if (page != null) {
      locator.put("page", page);
    }
    if (pageDocumentId != null) {
      locator.put("pageDocumentId", pageDocumentId);
    }
  }

  private static Evidence firstEvidence(NoticeDetailResponse detail) {
    return detail.schedules().getFirst().evidence().getFirst();
  }

  @Test
  void S3에_있는_PDF만_앱_안_경로를_주고_근거는_실린_PDF를_가리킨다() {
    NoticeDetailResponse detail =
        map(
            p -> {
              pdf(p, "file-1", 3, "https://example.org/a.pdf");
              pdf(p, "file-2", 2, null);
              pdf(p, "file-3", 4, "https://example.org/c.pdf"); // 우리 저장소에 없음
              located(p, "file-1", "raw/lh/1/v1/00-a.pdf");
              located(p, "file-2", "raw/lh/1/v1/01-b.pdf");
              evidenceOn(p, 2, "file-2");
            });

    assertThat(detail.files())
        .extracting(FileLink::id, FileLink::viewUrl, FileLink::pageCount)
        .containsExactly(
            org.assertj.core.groups.Tuple.tuple("text1", null, null),
            org.assertj.core.groups.Tuple.tuple(
                "file-1", "/api/v1/notices/" + ID + "/files/file-1", 3),
            org.assertj.core.groups.Tuple.tuple(
                "file-2", "/api/v1/notices/" + ID + "/files/file-2", 2),
            org.assertj.core.groups.Tuple.tuple("file-3", null, 4));
    assertThat(detail.files().get(2).url()).isNull(); // 기관 주소가 없어도 앱 안에서 열 수 있으면 넣어요
    Evidence e = firstEvidence(detail);
    assertThat(e.page()).isEqualTo(2);
    assertThat(e.fileId()).isEqualTo("file-2");
  }

  @Test
  void 실린_PDF가_없으면_글자를_읽은_PDF가_하나일_때만_그_PDF로_본다() {
    Evidence one =
        firstEvidence(
            map(
                p -> {
                  pdf(p, "file-1", 3, null);
                  pdf(p, "file-2", null, null); // 글자를 못 읽은 PDF(스캔본)는 원문 글자에 없어요
                  evidenceOn(p, 2, null);
                }));
    assertThat(one.fileId()).isEqualTo("file-1");

    Evidence two =
        firstEvidence(
            map(
                p -> {
                  pdf(p, "file-1", 3, null);
                  pdf(p, "file-2", 5, null);
                  evidenceOn(p, 2, null);
                }));
    assertThat(two.page()).isEqualTo(2);
    assertThat(two.fileId()).isNull(); // 어느 PDF의 2쪽인지 몰라요

    Evidence noPage =
        firstEvidence(
            map(
                p -> {
                  pdf(p, "file-1", 3, null);
                  evidenceOn(p, null, null);
                }));
    assertThat(noPage.fileId()).isNull();

    Evidence notPdf =
        firstEvidence(
            map(
                p -> {
                  pdf(p, "file-1", 3, null);
                  evidenceOn(p, 2, "text1"); // PDF가 아닌 문서는 가리키지 않아요
                }));
    assertThat(notPdf.fileId()).isNull();
  }

  @Test
  void 보류한_문서_PDF가_아닌_문서_raw_밖의_위치는_내려주지_않는다() {
    var pdfs =
        NoticeDetailMapper.sourcePdfs(
            withPayload(
                p -> {
                  pdf(p, "file-1", 3, null);
                  pdf(p, "file-2", 3, null);
                  pdf(p, "file-3", 3, null);
                  located(p, "file-1", "raw/lh/1/v1/00-a.pdf");
                  located(p, "file-2", "area/x.csv");
                  located(p, "file-3", "raw/lh/../../area/x.pdf");
                  located(p, "text1", "raw/lh/1/v1/text.txt");
                }));
    assertThat(pdfs).containsOnlyKeys("file-1");
    assertThat(pdfs.get("file-1").s3Key()).isEqualTo("raw/lh/1/v1/00-a.pdf");
    assertThat(pdfs.get("file-1").sha256()).isEqualTo(SHA);

    NoticeDetailResponse held =
        map(
            p -> {
              pdf(p, "file-1", 3, "https://example.org/a.pdf");
              located(p, "file-1", "raw/lh/1/v1/00-a.pdf");
              p.get("notice")
                  .get("quality")
                  .withArray("heldItems")
                  .addObject()
                  .put("target", "/documents/1")
                  .put("reason", "NEEDS_REVIEW")
                  .put("description", "원문 확인");
            });
    assertThat(held.files()).extracting(FileLink::id).containsExactly("text1");
  }

  private static ObjectNode withPayload(Consumer<ObjectNode> change) {
    ObjectNode p = NoticeFixtures.payload(UUID.randomUUID(), 1);
    change.accept(p);
    return p;
  }
}
