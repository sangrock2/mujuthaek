package kr.mujuthaek.api.notice.service.internal;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.UUID;
import java.util.stream.Stream;
import kr.mujuthaek.api.area.service.AreaReportService;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.notice.dto.response.AdminReportListResponse;
import kr.mujuthaek.api.notice.dto.response.AdminReportQueueResponse;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse;
import kr.mujuthaek.api.notice.repository.NoticeReportRepository;
import kr.mujuthaek.api.notice.repository.NoticeReportRepository.Report;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import org.junit.jupiter.api.Test;

/** 관리자 제보 대기열: 공고 제보와 생활권 제보를 최신순으로 섞어 페이지로 줄 때 빠지거나 겹치지 않아요. */
class AdminReportQueueServiceTest {

  private static final OffsetDateTime T0 =
      OffsetDateTime.of(2026, 10, 30, 0, 0, 0, 0, ZoneOffset.UTC);
  private static final UUID NOTICE = UUID.fromString("00000000-0000-4000-8000-0000000000aa");

  private final NoticeReportRepository repo = mock(NoticeReportRepository.class);
  private final NoticeReportService items = mock(NoticeReportService.class);
  private final AreaReportService areas = mock(AreaReportService.class);
  private final NoticeQueryService notices = mock(NoticeQueryService.class);
  private final List<Report> reports = new ArrayList<>();
  private final List<AreaReportService.QueueRow> areaRows = new ArrayList<>();

  private static UUID id(int n) {
    return UUID.fromString("00000000-0000-4000-8000-%012d".formatted(n));
  }

  private AdminReportQueueService service() {
    // 공고 제보 7건(분 0·2·4·…·12)과 생활권 제보 5건(분 1·3·5·…·9), 같은 시각 둘(분 12)도 섞어요
    for (int i = 0; i < 7; i++) {
      reports.add(report(id(i), T0.plusMinutes(i * 2L)));
    }
    reports.add(report(id(7), T0.plusMinutes(12)));
    for (int i = 0; i < 5; i++) {
      areaRows.add(area(id(100 + i), T0.plusMinutes(i * 2L + 1)));
    }
    when(repo.page(eq("NEW"), any(), any(), anyInt()))
        .thenAnswer(
            a ->
                page(
                    reports.stream(),
                    Report::createdAt,
                    Report::id,
                    a.getArgument(1),
                    a.getArgument(2),
                    a.getArgument(3)));
    when(areas.page(eq("NEW"), any(), any(), anyInt()))
        .thenAnswer(
            a ->
                page(
                    areaRows.stream(),
                    AreaReportService.QueueRow::createdAt,
                    AreaReportService.QueueRow::id,
                    a.getArgument(1),
                    a.getArgument(2),
                    a.getArgument(3)));
    when(items.item(any()))
        .thenAnswer(
            a -> {
              Report r = a.getArgument(0);
              return new AdminReportListResponse.Item(
                  r.id(),
                  r.status(),
                  "공고 상세",
                  "NOTICE",
                  r.noticeId(),
                  null,
                  null,
                  null,
                  r.noticeTitle(),
                  r.field(),
                  null,
                  null,
                  null,
                  r.createdAt(),
                  1,
                  null);
            });
    var header = mock(NoticeDetailResponse.Header.class);
    when(header.title()).thenReturn("가상 행복주택");
    var site = mock(NoticeDetailResponse.Site.class);
    when(site.id()).thenReturn("loc-1");
    when(site.name()).thenReturn("가상 단지");
    var detail = mock(NoticeDetailResponse.class);
    when(detail.header()).thenReturn(header);
    when(detail.sites()).thenReturn(List.of(site));
    when(notices.detail(NOTICE)).thenReturn(detail);
    return new AdminReportQueueService(repo, items, areas, notices);
  }

  /** 최신순, before(시각·ID)보다 오래된 것부터 limit건: 저장소 쿼리와 같은 규칙. */
  private static <T> List<T> page(
      Stream<T> all,
      java.util.function.Function<T, OffsetDateTime> at,
      java.util.function.Function<T, UUID> id,
      OffsetDateTime beforeAt,
      UUID beforeId,
      int limit) {
    Comparator<T> desc = Comparator.comparing(at).thenComparing(id).reversed();
    return all.filter(
            x ->
                beforeAt == null
                    || at.apply(x).isBefore(beforeAt)
                    || (at.apply(x).isEqual(beforeAt) && id.apply(x).compareTo(beforeId) < 0))
        .sorted(desc)
        .limit(limit)
        .toList();
  }

  private static Report report(UUID id, OffsetDateTime at) {
    return new Report(
        id,
        NOTICE,
        null,
        null,
        "가상 공고",
        UUID.randomUUID(),
        "DEADLINE",
        null,
        null,
        null,
        "공고 상세",
        "NEW",
        null,
        null,
        null,
        at,
        null,
        null,
        null,
        1);
  }

  private static AreaReportService.QueueRow area(UUID id, OffsetDateTime at) {
    return new AreaReportService.QueueRow(
        id, "NEW", "공고 상세", NOTICE, "loc-1", "STATION", null, null, null, at, 1, null);
  }

  @Test
  void 섞은_목록을_끝까지_넘겨도_빠지거나_겹치지_않고_최신순이다() {
    var service = service();
    List<AdminReportQueueResponse.Item> seen = new ArrayList<>();
    String cursor = null;
    int pages = 0;
    do {
      var page = service.queue("NEW", cursor, 3);
      assertThat(page.items()).hasSizeLessThanOrEqualTo(3);
      seen.addAll(page.items());
      cursor = page.nextCursor();
      pages++;
    } while (cursor != null && pages < 20);

    assertThat(cursor).isNull();
    assertThat(seen).hasSize(13);
    assertThat(seen).extracting(AdminReportQueueResponse.Item::id).doesNotHaveDuplicates();
    assertThat(seen)
        .extracting(AdminReportQueueResponse.Item::createdAt)
        .isSortedAccordingTo(Comparator.reverseOrder());
    // 생활권 제보는 「공고 이름 · 단지 이름」
    assertThat(seen)
        .filteredOn(i -> i.kind().equals("AREA"))
        .extracting(AdminReportQueueResponse.Item::title)
        .containsOnly("가상 행복주택 · 가상 단지");
    assertThat(seen)
        .filteredOn(i -> i.kind().equals("REPORT"))
        .extracting(AdminReportQueueResponse.Item::title)
        .containsOnly("가상 공고");
  }

  @Test
  void 상태와_커서와_크기가_틀리면_400() {
    var service = service();
    assertThatThrownBy(() -> service.queue("OPEN", null, 20)).isInstanceOf(CustomException.class);
    assertThatThrownBy(() -> service.queue("NEW", "깨진커서", 20)).isInstanceOf(CustomException.class);
    assertThatThrownBy(() -> service.queue("NEW", null, 0)).isInstanceOf(CustomException.class);
  }
}
