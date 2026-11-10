package kr.mujuthaek.api.notice.service;

import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import kr.mujuthaek.api.benefit.service.BenefitQueryService;
import kr.mujuthaek.api.benefit.service.BenefitSummary;
import kr.mujuthaek.api.common.dto.response.MyReportResponse;
import kr.mujuthaek.api.common.text.ScreenPaths;
import kr.mujuthaek.api.notice.repository.NoticeReportRepository;
import kr.mujuthaek.api.notice.repository.NoticeReportRepository.Report;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 회원이 보낸 공고·혜택·창업지원 사업·일반 제보 (내 정보의 「내 제보」). */
@Service
public class NoticeReportQueryService {

  private final NoticeReportRepository reports;
  private final NoticeQueryService notices;
  private final BenefitQueryService benefits;

  public NoticeReportQueryService(
      NoticeReportRepository reports, NoticeQueryService notices, BenefitQueryService benefits) {
    this.reports = reports;
    this.notices = notices;
    this.benefits = benefits;
  }

  /** 최근 것부터 limit건 */
  @Transactional(readOnly = true)
  public List<MyReportResponse> mine(UUID reporterId, int limit) {
    List<Report> rows = reports.byReporter(reporterId, limit);
    Map<UUID, NoticeSummary> noticeSummaries =
        notices.findSummaries(
            rows.stream().map(Report::noticeId).filter(Objects::nonNull).toList());
    return rows.stream().map(r -> item(r, noticeSummaries)).toList();
  }

  private MyReportResponse item(Report r, Map<UUID, NoticeSummary> noticeSummaries) {
    String kind;
    UUID targetId;
    String linkPath;
    if (r.noticeId() != null) {
      kind = "NOTICE";
      NoticeSummary n = noticeSummaries.get(r.noticeId());
      targetId = n == null ? r.noticeId() : n.noticeId(); // 합쳐진 공고는 남은 공고로
      linkPath = ScreenPaths.notice(targetId, n == null ? null : n.field());
    } else if (r.benefitPolicyId() != null) {
      kind = "BENEFIT";
      // 제보는 원본 정책 ID로 받지만 혜택 화면은 혜택 ID를 써요
      targetId =
          benefits
              .findSummaryByRawPolicyId(r.benefitPolicyId())
              .map(BenefitSummary::benefitId)
              .orElse(null);
      linkPath = targetId == null ? null : ScreenPaths.of("BENEFIT", targetId);
    } else if (r.rawPolicyId() != null) {
      kind = "PROGRAM";
      targetId = r.rawPolicyId();
      // 창업지원 사업은 사업 지원 상세, 사업공간 모집은 사업공간 상세
      String field =
          notices.findPolicySummary(targetId).map(PolicySummary::field).orElse("STARTUP_SUPPORT");
      linkPath = ScreenPaths.of(field, targetId);
    } else {
      kind = "GENERAL";
      targetId = null;
      linkPath = null;
    }
    return new MyReportResponse(
        r.id(),
        kind,
        targetId,
        r.noticeTitle(),
        r.field(),
        r.reportedValue(),
        r.note(),
        r.status(),
        r.result(),
        r.reply(),
        r.createdAt(),
        r.handledAt(),
        linkPath);
  }
}
