package kr.mujuthaek.api.notification.service.internal;

import java.time.Clock;
import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;
import kr.mujuthaek.api.common.event.PolicyPublished;
import kr.mujuthaek.api.common.event.PolicyUpdated;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import kr.mujuthaek.api.notice.service.PolicySummary;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * notice의 정책 내부 이벤트(PolicyPublished·PolicyUpdated)를 알림 서버로 보낼 notification.requested로 바꿔 아웃박스에 적어요
 * (contracts/schemas/notification-events.draft.md). 창업지원 사업·사업공간 모집은 notice.policy_judgments에 있어요.
 * 저장과 같은 트랜잭션에서 불러요.
 *
 * <ul>
 *   <li>PolicyPublished → NEW_SUPPORT (관심 조건 business_interests가 맞는 회원)
 *   <li>PolicyUpdated → CORRECTED (관심 정책으로 둔 회원). 알릴 부분이 바뀌었을 때만
 * </ul>
 *
 * <p>과거 자료 재처리(reprocess), 이미 마감됐거나 마감일을 모르는데 상시도 아닌(판정 목록에 안 보이는) 정책의 새 소식은 보내지 않아요. 적는 방법은 {@link
 * NotificationRequests}.
 */
@Service
public class PolicyNotificationService {

  /** 정정 알림에 넣을 부분과 문구 이름 (PolicyUpdated.changedFields). 제목·지역은 알리지 않아요 */
  static final Map<String, String> ALERT_LABELS = labels();

  private final NoticeQueryService notices;
  private final RecipientFinder recipients;
  private final NotificationRequests requests;
  private final Clock clock;

  public PolicyNotificationService(
      NoticeQueryService notices,
      RecipientFinder recipients,
      NotificationRequests requests,
      Clock clock) {
    this.notices = notices;
    this.recipients = recipients;
    this.requests = requests;
    this.clock = clock;
  }

  /** 새 정책 → NEW_SUPPORT. 보낸 요청 수를 돌려줘요 */
  @Transactional(propagation = Propagation.MANDATORY)
  public int onPublished(PolicyPublished event) {
    if (event.reprocess()) {
      return 0;
    }
    Optional<PolicySummary> found = notices.findPolicySummary(event.policyId());
    if (found.isEmpty()) {
      return 0;
    }
    PolicySummary p = found.get();
    if ("CLOSED".equals(p.status()) || "UNKNOWN".equals(p.status())) {
      return 0; // 마감됐거나 판정 목록에 안 보이는 정책은 새 소식으로 알리지 않아요
    }
    String kind = NotificationRequests.kind(p.field());
    String type = NotificationRequests.targetType(p.field());
    return requests.write(
        "NEW_SUPPORT",
        type + ":" + p.policyId() + ":NEW",
        type,
        p.policyId(),
        "새 " + kind + ": " + p.title(),
        "관심 조건에 맞는 새 " + kind + " 소식이에요." + summary(p),
        recipients.forNewBenefit(
            p.field(), p.regionCodes().isEmpty() ? "NATIONWIDE" : "SIGUNGU", p.regionCodes()));
  }

  /** 바뀐 정책 → CORRECTED. 알릴 부분이 없으면 보내지 않아요 */
  @Transactional(propagation = Propagation.MANDATORY)
  public int onUpdated(PolicyUpdated event) {
    if (event.reprocess()) {
      return 0;
    }
    String labels =
        event.changedFields().stream()
            .map(ALERT_LABELS::get)
            .filter(java.util.Objects::nonNull)
            .collect(Collectors.joining(", "));
    if (labels.isEmpty()) {
      return 0;
    }
    Optional<PolicySummary> found = notices.findPolicySummary(event.policyId());
    if (found.isEmpty()) {
      return 0;
    }
    PolicySummary p = found.get();
    String type = NotificationRequests.targetType(p.field());
    return requests.write(
        "CORRECTED",
        type + ":" + p.policyId() + ":CORRECTED:" + event.version(),
        type,
        p.policyId(),
        "정정: " + p.title(),
        "관심 " + NotificationRequests.kind(p.field()) + "의 " + labels + " 내용이 바뀌었어요.",
        recipients.forFavorite(type, p.policyId(), "CORRECTED"));
  }

  private String summary(PolicySummary p) {
    StringBuilder sb = new StringBuilder();
    if (p.organization() != null && !p.organization().isBlank()) {
      sb.append(' ').append(p.organization());
    }
    if ("ALWAYS".equals(p.status())) {
      sb.append(sb.isEmpty() ? " " : " · ").append("상시 모집");
    } else if (p.applyEnd() != null && !p.applyEnd().isBefore(LocalDate.now(clock))) {
      sb.append(sb.isEmpty() ? " " : " · ")
          .append(NotificationRequests.monthDay(p.applyEnd()))
          .append(" 마감");
    } else if (p.applyEnd() == null && p.applyNote() != null && !p.applyNote().isBlank()) {
      // 마감일 대신 신청 기간 안내만 있는 정책(「예산 소진 시까지」): 그 안내를 적어요(2026-11-10 재검토: 신청 기간 정보 없이 나갔음)
      sb.append(sb.isEmpty() ? " " : " · ").append(p.applyNote().strip());
    }
    return sb.toString();
  }

  private static Map<String, String> labels() {
    Map<String, String> m = new LinkedHashMap<>();
    m.put("schedule", "일정");
    m.put("conditions", "자격");
    m.put("application", "신청 방법");
    return java.util.Collections.unmodifiableMap(m);
  }
}
