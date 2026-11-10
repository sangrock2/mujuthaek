package kr.mujuthaek.api.user.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.api.area.service.AreaReportService;
import kr.mujuthaek.api.common.dto.response.MyReportResponse;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import kr.mujuthaek.api.notice.service.NoticeReportQueryService;
import kr.mujuthaek.api.notice.service.NoticeSummary;
import org.junit.jupiter.api.Test;

/** 내 제보: 공고 쪽 제보와 생활권 제보를 합쳐 최근 것부터, 생활권 제보에는 공고 제목·화면을 채워요 (DB 없이). */
class MyReportServiceTest {

  final NoticeReportQueryService noticeReports = mock(NoticeReportQueryService.class);
  final AreaReportService areaReports = mock(AreaReportService.class);
  final NoticeQueryService notices = mock(NoticeQueryService.class);
  final MyReportService service = new MyReportService(noticeReports, areaReports, notices);
  final UUID me = UUID.randomUUID();

  @Test
  void mergesNewestFirstAndFillsAreaReportTitles() {
    UUID asked = UUID.randomUUID();
    UUID remaining = UUID.randomUUID();
    MyReportResponse general = report("GENERAL", null, "2026-10-29T10:00:00+09:00");
    MyReportResponse area = report("AREA", asked, "2026-10-29T11:00:00+09:00");
    MyReportResponse notice = report("NOTICE", UUID.randomUUID(), "2026-10-29T09:00:00+09:00");
    when(noticeReports.mine(me, MyReportService.LIMIT)).thenReturn(List.of(general, notice));
    when(areaReports.mine(me, MyReportService.LIMIT)).thenReturn(List.of(area));
    when(notices.findSummaries(any()))
        .thenReturn(
            Map.of(
                asked,
                new NoticeSummary(
                    remaining,
                    1,
                    "HOUSING",
                    "서리풀 아트타운",
                    "SH",
                    null,
                    "APPLYING",
                    null,
                    null,
                    List.of(),
                    false,
                    "/",
                    null)));

    List<MyReportResponse> mine = service.mine(me);

    assertThat(mine)
        .extracting(MyReportResponse::kind)
        .containsExactly("AREA", "GENERAL", "NOTICE");
    MyReportResponse filled = mine.getFirst();
    assertThat(filled.targetId()).isEqualTo(remaining); // 합쳐진 공고는 남은 공고로
    assertThat(filled.targetTitle()).isEqualTo("서리풀 아트타운");
    assertThat(filled.linkPath()).isEqualTo("/notices/" + remaining);
  }

  private static MyReportResponse report(String kind, UUID target, String at) {
    return new MyReportResponse(
        UUID.randomUUID(),
        kind,
        target,
        null,
        "칸",
        null,
        "설명",
        "NEW",
        null,
        null,
        OffsetDateTime.parse(at),
        null,
        target == null ? null : "/notices/" + target);
  }
}
