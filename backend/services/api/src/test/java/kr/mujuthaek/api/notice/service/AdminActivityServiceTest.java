package kr.mujuthaek.api.notice.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.api.area.service.AreaReportService;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.notice.client.ExtractionReviewClient;
import kr.mujuthaek.api.notice.repository.NoticeReportRepository;
import kr.mujuthaek.api.notice.repository.NoticeReportRepository.Report;
import kr.mujuthaek.api.notice.service.internal.AdminActivityService;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

/** 처리 기록: 검수·제보 처리를 최근 순으로 모으고, 추출 서비스가 꺼져도 제보 기록은 보여요 (DB 없이). */
class AdminActivityServiceTest {

  final ExtractionReviewClient extraction = mock(ExtractionReviewClient.class);
  final NoticeReportRepository reports = mock(NoticeReportRepository.class);
  final AreaReportService area = mock(AreaReportService.class);
  final NoticeQueryService notices = mock(NoticeQueryService.class);
  final AdminActivityService service =
      new AdminActivityService(
          extraction,
          reports,
          area,
          notices,
          Clock.fixed(Instant.parse("2026-10-27T03:00:00Z"), ZoneOffset.UTC));

  final UUID notice = UUID.randomUUID();
  final UUID areaNotice = UUID.randomUUID();

  private Report report(UUID id, UUID noticeId, UUID benefitId, String title, String at) {
    return new Report(
        id,
        noticeId,
        noticeId == null && benefitId == null ? UUID.randomUUID() : null,
        benefitId,
        title,
        UUID.randomUUID(),
        "보증금",
        null,
        null,
        null,
        null,
        "DONE",
        "FIXED",
        "고쳤어요",
        "admin-1",
        OffsetDateTime.parse(at),
        null,
        OffsetDateTime.parse(at),
        null,
        0);
  }

  @Test
  void 검수와_제보_처리를_최근_순으로_모은다() {
    when(extraction.activity(30))
        .thenReturn(
            JsonMapper.builder()
                .build()
                .readTree(
                    "{\"items\":[{\"kind\":\"NOTICE\",\"id\":\"job-1\",\"title\":\"행복주택\","
                        + "\"action\":\"EDITED_APPROVED\",\"at\":\"2026-10-26T10:00:00Z\","
                        + "\"by\":\"admin-2\",\"note\":null},"
                        + "{\"kind\":\"BENEFIT\",\"id\":\"rv-1\",\"title\":\"청년 월세\","
                        + "\"action\":\"REJECTED\",\"at\":\"2026-10-25 10:00:00.473631+00:00\","
                        + "\"by\":\"admin-1\",\"note\":\"서비스 대상 아님\"}]}"));
    UUID r1 = UUID.randomUUID();
    UUID r2 = UUID.randomUUID();
    when(reports.handledSince(any(), anyInt()))
        .thenReturn(
            List.of(
                report(r1, notice, null, "서리풀 청년아트타운", "2026-10-26T12:00:00Z"),
                report(r2, null, UUID.randomUUID(), "청년 월세", "2026-10-24T12:00:00Z")));
    UUID a1 = UUID.randomUUID();
    when(area.handledSince(any(), anyInt()))
        .thenReturn(
            List.of(
                new AreaReportService.Handled(
                    a1,
                    areaNotice,
                    "역까지 거리",
                    "KEPT",
                    "admin-1",
                    OffsetDateTime.parse("2026-10-26T11:00:00Z"))));
    NoticeSummary summary = mock(NoticeSummary.class);
    when(summary.title()).thenReturn("구리갈매 공공임대");
    when(notices.findSummaries(eq(List.of(areaNotice)))).thenReturn(Map.of(areaNotice, summary));

    var res = service.activity(30);

    assertThat(res.reviewsError()).isNull();
    assertThat(res.items())
        .extracting(i -> i.kind() + "/" + i.action() + "/" + i.title() + "/" + i.by())
        .containsExactly(
            "NOTICE_REPORT/FIXED/서리풀 청년아트타운/admin-1",
            "AREA_REPORT/KEPT/구리갈매 공공임대/admin-1",
            "NOTICE_REVIEW/EDITED_APPROVED/행복주택/admin-2",
            "BENEFIT_REVIEW/REJECTED/청년 월세/admin-1",
            "BENEFIT_REPORT/FIXED/청년 월세/admin-1");
  }

  @Test
  void 추출_서비스가_꺼져도_제보_기록은_준다() {
    when(extraction.activity(7))
        .thenThrow(new CustomException(ErrorCode.NOTICE_REVIEW_UNAVAILABLE));
    when(reports.handledSince(any(), anyInt()))
        .thenReturn(List.of(report(UUID.randomUUID(), notice, null, "공고", "2026-10-26T12:00:00Z")));
    when(area.handledSince(any(), anyInt())).thenReturn(List.of());
    when(notices.findSummaries(any())).thenReturn(Map.of());

    var res = service.activity(7);

    assertThat(res.reviewsError()).isNotBlank();
    assertThat(res.items())
        .singleElement()
        .satisfies(i -> assertThat(i.kind()).isEqualTo("NOTICE_REPORT"));
  }
}
