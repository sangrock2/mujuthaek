package kr.mujuthaek.api.notification.service.internal;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.OptionalInt;
import java.util.UUID;
import kr.mujuthaek.api.benefit.service.BenefitQueryService;
import kr.mujuthaek.api.benefit.service.BenefitSummary;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import kr.mujuthaek.api.notice.service.NoticeSummary;
import kr.mujuthaek.api.notice.service.PolicySummary;
import kr.mujuthaek.api.notification.repository.ReminderRunRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 마감 D-3·D-1 알림 (contracts/schemas/notification-events.draft.md). 매일 한국 시간 11:00 이후 처음 확인할 때 한 번,
 * 마감일이 3일 뒤·1일 뒤인 접수 중인 주거·사업공간 공고, 지원 정책, 창업지원 사업·사업공간 모집(notice 정책)을 관심 공고로 둔 회원에게
 * DEADLINE_D3·DEADLINE_D1을 남기고 보내요.
 *
 * <ul>
 *   <li>하루 한 번: 실행 기록(reminder_runs)에 그날 줄을 먼저 넣은 서버만 해요. 서버가 여러 대여도 같은 요청이 두 번 생기지 않아요
 *   <li>따라잡기: 11:00에 서버가 꺼져 있었어도 그날 다음 확인 때 해요. 지난 날짜는 다시 하지 않아요(어제의 D-1은 이미 마감일이라)
 *   <li>한 트랜잭션: 실행 기록과 알림 요청이 함께 커밋돼요. 중간에 실패하면 둘 다 되돌려지고 다음 확인 때 다시 해요
 *   <li>정정으로 마감일이 바뀌면 dedupKey에 새 마감일이 들어가 새 날짜 기준으로 다시 알려요
 * </ul>
 */
@Service
public class DeadlineReminderService {

  private static final Logger log = LoggerFactory.getLogger(DeadlineReminderService.class);

  static final String KIND = "DEADLINE";
  static final ZoneId KOREA = ZoneId.of("Asia/Seoul");
  static final LocalTime SEND_AT = LocalTime.of(11, 0); // 운영 서버는 낮(10시~)에만 켜져 있어요

  private final BenefitQueryService benefits;
  private final NoticeQueryService notices;
  private final RecipientFinder recipients;
  private final ReminderRunRepository runs;
  private final NotificationRequests requests;
  private final Clock clock;

  public DeadlineReminderService(
      BenefitQueryService benefits,
      NoticeQueryService notices,
      RecipientFinder recipients,
      ReminderRunRepository runs,
      NotificationRequests requests,
      Clock clock) {
    this.benefits = benefits;
    this.notices = notices;
    this.recipients = recipients;
    this.runs = runs;
    this.requests = requests;
    this.clock = clock;
  }

  /** 오늘 할 차례면 하고 적은 요청 수를, 아직 11:00 전이거나 오늘 이미 했으면 빈 값을 돌려줘요 */
  @Transactional
  public OptionalInt runIfDue() {
    Instant now = clock.instant();
    ZonedDateTime local = now.atZone(KOREA);
    if (local.toLocalTime().isBefore(SEND_AT)) {
      return OptionalInt.empty();
    }
    LocalDate today = local.toLocalDate();
    if (!runs.claim(today, KIND, now)) {
      return OptionalInt.empty();
    }
    List<LocalDate> dates = List.of(today.plusDays(3), today.plusDays(1));
    List<BenefitSummary> closing = benefits.findOpenClosingOn(dates, today);
    List<NoticeSummary> closingNotices = notices.findOpenClosingOn(dates, today);
    List<PolicySummary> closingPolicies = notices.findOpenPoliciesClosingOn(dates, today);
    int requested = 0;
    for (BenefitSummary b : closing) {
      requested += remind(b, today);
    }
    for (NoticeSummary n : closingNotices) {
      requested +=
          remind(
              NoticeNotificationService.TARGET,
              NoticeNotificationService.KIND,
              n.noticeId(),
              NotificationRequests.noticeLink(n.noticeId(), n.field()),
              n.title(),
              n.applyEnd(),
              today);
    }
    for (PolicySummary p : closingPolicies) {
      requested +=
          remind(
              NotificationRequests.targetType(p.field()),
              NotificationRequests.kind(p.field()),
              p.policyId(),
              NotificationRequests.linkPath(
                  NotificationRequests.targetType(p.field()), p.policyId()),
              p.title(),
              p.applyEnd(),
              today);
    }
    runs.finish(today, KIND, requested);
    log.info(
        "마감 알림 작업: 날짜={}, 마감 임박 정책={}건·공고={}건·창업지원·사업공간 모집={}건, 요청={}",
        today,
        closing.size(),
        closingNotices.size(),
        closingPolicies.size(),
        requested);
    return OptionalInt.of(requested);
  }

  private int remind(BenefitSummary b, LocalDate today) {
    return remind(
        NotificationRequests.targetType(b.field()),
        NotificationRequests.kind(b.field()),
        b.benefitId(),
        NotificationRequests.linkPath(NotificationRequests.targetType(b.field()), b.benefitId()),
        b.title(),
        b.applyEnd(),
        today);
  }

  /** {@code kind}는 문구의 {종류} (공고 · 지원 정책 …) */
  private int remind(
      String targetType,
      String kind,
      UUID id,
      String linkPath,
      String title,
      LocalDate applyEnd,
      LocalDate today) {
    boolean threeDays = ChronoUnit.DAYS.between(today, applyEnd) == 3;
    String day = NotificationRequests.monthDay(applyEnd);
    String type = threeDays ? "DEADLINE_D3" : "DEADLINE_D1";
    return requests.write(
        type,
        targetType + ":" + id + (threeDays ? ":D3:" : ":D1:") + applyEnd,
        targetType,
        id,
        linkPath,
        (threeDays ? "마감 3일 전: " : "내일 마감: ") + title,
        threeDays
            ? "관심 " + kind + " 접수가 " + day + "에 마감돼요."
            : "관심 " + kind + " 접수가 내일(" + day + ") 마감돼요.",
        recipients.forFavorite(targetType, id, type));
  }
}
