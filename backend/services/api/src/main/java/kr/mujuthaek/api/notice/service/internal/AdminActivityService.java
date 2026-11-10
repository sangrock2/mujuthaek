package kr.mujuthaek.api.notice.service.internal;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import kr.mujuthaek.api.area.service.AreaReportService;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.notice.client.ExtractionReviewClient;
import kr.mujuthaek.api.notice.dto.response.AdminActivityResponse;
import kr.mujuthaek.api.notice.dto.response.AdminActivityResponse.Item;
import kr.mujuthaek.api.notice.repository.NoticeReportRepository;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import kr.mujuthaek.api.notice.service.NoticeSummary;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;

/**
 * 관리자 「처리 기록」을 모아요: 검수 처리(추출 서비스 /reviews/activity)와 공고·혜택·창업 사업 제보(notice), 생활권 제보(area). 기준값 변경과
 * 권한 변경은 각 모듈 API를 화면이 같이 불러요(notice가 eligibility·user를 부를 수 없어서).
 */
@Service
public class AdminActivityService {

  private static final int LIMIT = 300;

  private final ExtractionReviewClient extraction;
  private final NoticeReportRepository reports;
  private final AreaReportService areaReports;
  private final NoticeQueryService notices;
  private final Clock clock;

  public AdminActivityService(
      ExtractionReviewClient extraction,
      NoticeReportRepository reports,
      AreaReportService areaReports,
      NoticeQueryService notices,
      Clock clock) {
    this.extraction = extraction;
    this.reports = reports;
    this.areaReports = areaReports;
    this.notices = notices;
    this.clock = clock;
  }

  @Transactional(readOnly = true)
  public AdminActivityResponse activity(int days) {
    int d = Math.clamp(days, 1, 90);
    Instant since = clock.instant().minus(Duration.ofDays(d));
    List<Item> items = new ArrayList<>();
    String reviewsError = null;
    try {
      for (JsonNode x : extraction.activity(d).path("items")) {
        items.add(
            new Item(
                AdminReviewService.time(x.path("at")),
                "BENEFIT".equals(x.path("kind").asString()) ? "BENEFIT_REVIEW" : "NOTICE_REVIEW",
                x.path("action").asString(),
                text(x, "title"),
                text(x, "note"),
                text(x, "by"),
                text(x, "id")));
      }
    } catch (CustomException e) {
      reviewsError = e.getMessage();
    }
    for (var r : reports.handledSince(since, LIMIT)) {
      String kind =
          r.noticeId() != null
              ? "NOTICE_REPORT"
              : r.benefitPolicyId() != null ? "BENEFIT_REPORT" : "PROGRAM_REPORT";
      items.add(
          new Item(
              r.handledAt(),
              kind,
              r.result(),
              r.noticeTitle(),
              r.field(),
              r.handledBy(),
              r.id().toString()));
    }
    var area = areaReports.handledSince(since, LIMIT);
    var titles =
        notices.findSummaries(area.stream().map(AreaReportService.Handled::noticeId).toList());
    for (var r : area) {
      NoticeSummary notice = titles.get(r.noticeId());
      items.add(
          new Item(
              r.handledAt(),
              "AREA_REPORT",
              r.result(),
              notice == null ? null : notice.title(),
              r.field(),
              r.handledBy(),
              r.id().toString()));
    }
    items.sort(Comparator.comparing(Item::at, Comparator.nullsLast(Comparator.reverseOrder())));
    return new AdminActivityResponse(d, items.stream().limit(LIMIT).toList(), reviewsError);
  }

  private static String text(JsonNode node, String key) {
    JsonNode v = node.path(key);
    return v.isMissingNode() || v.isNull() ? null : v.asString();
  }
}
