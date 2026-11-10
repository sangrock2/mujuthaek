package kr.mujuthaek.api.notification.service.internal;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.benefit.service.BenefitQueryService;
import kr.mujuthaek.api.benefit.service.BenefitSummary;
import kr.mujuthaek.api.common.event.AreaReportAnswered;
import kr.mujuthaek.api.common.event.BenefitReportAnswered;
import kr.mujuthaek.api.common.event.GeneralReportAnswered;
import kr.mujuthaek.api.common.event.NoticeReportAnswered;
import kr.mujuthaek.api.common.event.ProgramReportAnswered;
import kr.mujuthaek.api.common.event.ReportAnswered;
import kr.mujuthaek.api.common.text.ScreenPaths;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import kr.mujuthaek.api.notice.service.NoticeSummary;
import kr.mujuthaek.api.notice.service.PolicySummary;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * 관리자가 제보를 처리하고 답을 남기면(ReportAnswered) 제보한 회원에게 REPORT_ANSWERED를 남기고 보내요
 * (contracts/schemas/notification-events.draft.md). 제보 처리와 같은 트랜잭션에서 불러요.
 *
 * <ul>
 *   <li>공고·생활권 제보 → 공고(NOTICE), 혜택 제보 → 혜택(BENEFIT, 수집 정책 ID로 찾음), 창업 사업 제보 → 창업지원
 *       사업(STARTUP_SUPPORT)
 *   <li>관리자 답변 원문(reply)은 회원 개인정보가 들어갈 수 있어 푸시·알림함 문구에 넣지 않아요. 문구는 처리 결과(고침·그대로 둠)만
 *   <li>알림 설정으로 끌 수 없고(본인 제보의 답장), 조용한 시간은 따라요. 제보마다 한 번
 * </ul>
 */
@Service
public class ReportAnsweredNotificationService {

  private static final Logger log =
      LoggerFactory.getLogger(ReportAnsweredNotificationService.class);

  static final String TYPE = "REPORT_ANSWERED";

  private final NoticeQueryService notices;
  private final BenefitQueryService benefits;
  private final RecipientFinder recipients;
  private final NotificationRequests requests;

  public ReportAnsweredNotificationService(
      NoticeQueryService notices,
      BenefitQueryService benefits,
      RecipientFinder recipients,
      NotificationRequests requests) {
    this.notices = notices;
    this.benefits = benefits;
    this.recipients = recipients;
    this.requests = requests;
  }

  /** 알림이 가리킬 대상. kind는 제보 종류 (dedupKey에 넣어요: 생활권 제보는 다른 표라 ID가 겹칠 수 있어서), linkPath는 누르면 갈 화면 */
  private record Target(
      String kind, String type, UUID id, String title, String subject, String linkPath) {}

  /** 보낸 요청 수를 돌려줘요 (대상을 찾을 수 없거나 기기가 없으면 0) */
  @Transactional(propagation = Propagation.MANDATORY)
  public int onAnswered(ReportAnswered event) {
    Optional<Target> found = target(event);
    if (found.isEmpty()) {
      log.warn(
          "제보 답변 알림의 대상을 찾지 못해 보내지 않아요: reportId={}, 종류={}",
          event.reportId(),
          event.getClass().getSimpleName());
      return 0;
    }
    Target t = found.get();
    String outcome = "FIXED".equals(event.result()) ? "확인하고 고쳤어요." : "확인했어요. 원문과 같아 그대로 두었어요.";
    return requests.write(
        TYPE,
        (t.type() == null ? "GENERAL" : t.type() + ":" + t.id())
            + ":ANSWERED:"
            + t.kind()
            + ":"
            + event.reportId(),
        t.type(),
        t.id(),
        t.linkPath(),
        t.title() == null || t.title().isBlank() ? "제보 답변이 도착했어요" : "제보 답변: " + t.title(),
        "제보하신 " + t.subject() + "'" + event.field() + "' 내용을 " + outcome,
        List.of(recipients.forReporter(event.reporterId())));
  }

  private Optional<Target> target(ReportAnswered event) {
    return switch (event) {
      case NoticeReportAnswered e -> notice("NOTICE", e.noticeId(), e.targetTitle(), "");
      case AreaReportAnswered e -> notice("AREA", e.noticeId(), e.targetTitle(), "생활권 ");
      // 일반 제보는 가리킬 대상이 없어요: 알림함에만 남기고 누르면 내 정보의 제보 탭으로
      case GeneralReportAnswered e ->
          Optional.of(new Target("GENERAL", null, null, null, "", ScreenPaths.MY_REPORTS));
      case BenefitReportAnswered e ->
          benefits
              .findSummaryByRawPolicyId(e.policyId())
              .map(BenefitSummary::benefitId)
              .map(
                  id ->
                      new Target(
                          "BENEFIT",
                          "BENEFIT",
                          id,
                          title(e.targetTitle(), () -> benefitTitle(e.policyId())),
                          "",
                          NotificationRequests.linkPath("BENEFIT", id)));
      case ProgramReportAnswered e -> {
        // 창업지원 사업은 사업 지원 상세, 사업공간 모집은 사업공간 상세로
        Optional<PolicySummary> summary = notices.findPolicySummary(e.programId());
        String type = summary.map(PolicySummary::field).orElse("STARTUP_SUPPORT");
        yield Optional.of(
            new Target(
                "PROGRAM",
                type,
                e.programId(),
                title(e.targetTitle(), () -> summary.map(PolicySummary::title).orElse(null)),
                "",
                NotificationRequests.linkPath(type, e.programId())));
      }
    };
  }

  /** 공고·생활권 제보: 다른 공고에 합쳐졌으면 남은 공고로 보내요. 공고가 숨겨졌거나 없어도 공고 ID로 보내요 (답은 받아야 해서) */
  private Optional<Target> notice(String kind, UUID noticeId, String title, String subject) {
    Optional<NoticeSummary> summary = notices.findSummary(noticeId);
    UUID id = summary.map(NoticeSummary::noticeId).orElse(noticeId);
    return Optional.of(
        new Target(
            kind,
            "NOTICE",
            id,
            title(title, () -> summary.map(NoticeSummary::title).orElse(null)),
            subject,
            NotificationRequests.noticeLink(id, summary.map(NoticeSummary::field).orElse(null))));
  }

  private String benefitTitle(UUID rawPolicyId) {
    return benefits.findSummaryByRawPolicyId(rawPolicyId).map(BenefitSummary::title).orElse(null);
  }

  private static String title(String given, java.util.function.Supplier<String> lookup) {
    return given != null && !given.isBlank() ? given : lookup.get();
  }
}
