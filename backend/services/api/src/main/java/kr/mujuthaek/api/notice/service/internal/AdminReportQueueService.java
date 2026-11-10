package kr.mujuthaek.api.notice.service.internal;

import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import kr.mujuthaek.api.area.service.AreaReportService;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.notice.dto.response.AdminReportQueueResponse;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse;
import kr.mujuthaek.api.notice.repository.NoticeReportRepository;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import org.springframework.stereotype.Service;

/**
 * 관리자 제보 대기열: 공고·혜택·사업 제보와 생활권 제보를 한 목록으로, 들어온 시각 최신순으로 size건씩 이어 받아요(무한 스크롤). 상태(NEW·DOING·DONE)마다
 * 따로 받고, 상태별 건수는 /api/admin/reports/counts·/api/admin/area-reports/counts가 줘요.
 */
@Service
public class AdminReportQueueService {

  /** 한 페이지 최대 건수. */
  public static final int MAX_SIZE = 100;

  private static final Set<String> STATUSES = Set.of("NEW", "DOING", "DONE");

  /** 최신순, 같은 시각이면 종류·ID 큰 것부터 (쪽마다 created_at desc, id desc로 받은 순서와 맞아요). */
  private static final Comparator<AdminReportQueueResponse.Item> ORDER =
      Comparator.comparing(AdminReportQueueResponse.Item::createdAt)
          .thenComparing(AdminReportQueueResponse.Item::kind)
          .thenComparing(AdminReportQueueResponse.Item::id)
          .reversed();

  private final NoticeReportRepository reports;
  private final NoticeReportService reportItems;
  private final AreaReportService areaReports;
  private final NoticeQueryService notices;

  public AdminReportQueueService(
      NoticeReportRepository reports,
      NoticeReportService reportItems,
      AreaReportService areaReports,
      NoticeQueryService notices) {
    this.reports = reports;
    this.reportItems = reportItems;
    this.areaReports = areaReports;
    this.notices = notices;
  }

  public AdminReportQueueResponse queue(String status, String cursor, int size) {
    if (!STATUSES.contains(status)) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "status는 NEW·DOING·DONE 중 하나예요");
    }
    if (size < 1 || size > MAX_SIZE) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "size는 1~" + MAX_SIZE + " 사이예요");
    }
    ReportQueueCursor at = ReportQueueCursor.decode(cursor);
    // 쪽마다 size+1건을 받아 다음이 있는지 알아요
    List<AdminReportQueueResponse.Item> fetchedReports =
        at.report().done()
            ? List.of()
            : reports.page(status, at.report().at(), at.report().id(), size + 1).stream()
                .map(reportItems::item)
                .map(AdminReportQueueService::fromReport)
                .toList();
    List<AreaReportService.QueueRow> areaRows =
        at.area().done()
            ? List.of()
            : areaReports.page(status, at.area().at(), at.area().id(), size + 1);
    List<AdminReportQueueResponse.Item> fetchedArea = areaItems(areaRows);
    List<AdminReportQueueResponse.Item> sent =
        Stream.concat(fetchedReports.stream(), fetchedArea.stream())
            .sorted(ORDER)
            .limit(size)
            .toList();
    ReportQueueCursor.Side nextReport = next(at.report(), fetchedReports, sent);
    ReportQueueCursor.Side nextArea = next(at.area(), fetchedArea, sent);
    String next =
        nextReport.done() && nextArea.done()
            ? null
            : new ReportQueueCursor(nextReport, nextArea).encode();
    return new AdminReportQueueResponse(sent, next);
  }

  /** 한 쪽의 다음 위치: 보낸 것 중 그 쪽의 마지막 건. 받은 것을 다 보냈고 더 없으면 끝. */
  private static ReportQueueCursor.Side next(
      ReportQueueCursor.Side side,
      List<AdminReportQueueResponse.Item> fetched,
      List<AdminReportQueueResponse.Item> sent) {
    if (side.done()) {
      return side;
    }
    List<AdminReportQueueResponse.Item> mine = sent.stream().filter(fetched::contains).toList();
    if (mine.size() == fetched.size()) {
      return ReportQueueCursor.Side.DONE; // size+1건을 다 못 받았으니 이게 끝이에요
    }
    if (mine.isEmpty()) {
      return side;
    }
    AdminReportQueueResponse.Item last = mine.getLast();
    return new ReportQueueCursor.Side(last.createdAt(), last.id(), false);
  }

  private static AdminReportQueueResponse.Item fromReport(
      kr.mujuthaek.api.notice.dto.response.AdminReportListResponse.Item r) {
    return new AdminReportQueueResponse.Item(
        "REPORT",
        r.id(),
        r.status(),
        r.screen(),
        r.targetType(),
        r.noticeId(),
        null,
        r.programId(),
        r.benefitPolicyId(),
        r.benefitId(),
        r.noticeTitle(),
        r.field(),
        r.currentValue(),
        r.reportedValue(),
        r.summary(),
        r.createdAt(),
        r.groupCount(),
        r.result());
  }

  /** 생활권 제보: 제목은 「공고 이름 · 단지 이름」. 공고를 못 보면(숨김·공개 전) 제목 없이. 페이지의 공고마다 한 번만 찾아요. */
  private List<AdminReportQueueResponse.Item> areaItems(List<AreaReportService.QueueRow> rows) {
    Map<UUID, NoticeDetailResponse> details = new HashMap<>();
    for (UUID id :
        rows.stream().map(AreaReportService.QueueRow::noticeId).collect(Collectors.toSet())) {
      try {
        details.put(id, notices.detail(id));
      } catch (CustomException e) {
        // 숨김·공개 전 공고는 제목 없이 보여요
      }
    }
    return rows.stream()
        .map(
            r -> {
              NoticeDetailResponse d = details.get(r.noticeId());
              String site =
                  d == null || r.noticeLocationId() == null
                      ? null
                      : d.sites().stream()
                          .filter(s -> r.noticeLocationId().equals(s.id()))
                          .map(NoticeDetailResponse.Site::name)
                          .filter(n -> n != null && !n.isBlank())
                          .findFirst()
                          .orElse(null);
              String title =
                  d == null
                      ? null
                      : site == null ? d.header().title() : d.header().title() + " · " + site;
              return new AdminReportQueueResponse.Item(
                  "AREA",
                  r.id(),
                  r.status(),
                  r.screen(),
                  "AREA",
                  r.noticeId(),
                  r.noticeLocationId(),
                  null,
                  null,
                  null,
                  title,
                  r.field(),
                  r.currentValue(),
                  r.reportedValue(),
                  r.summary(),
                  r.createdAt(),
                  r.groupCount(),
                  r.result());
            })
        .toList();
  }
}
