package kr.mujuthaek.api.notification;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.benefit.service.BenefitQueryService;
import kr.mujuthaek.api.benefit.service.BenefitSummary;
import kr.mujuthaek.api.common.event.AreaReportAnswered;
import kr.mujuthaek.api.common.event.BenefitReportAnswered;
import kr.mujuthaek.api.common.event.NoticeReportAnswered;
import kr.mujuthaek.api.common.event.ProgramReportAnswered;
import kr.mujuthaek.api.common.messaging.Outbox;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import kr.mujuthaek.api.notice.service.NoticeSummary;
import kr.mujuthaek.api.notice.service.PolicySummary;
import kr.mujuthaek.api.notification.repository.InboxRepository;
import kr.mujuthaek.api.notification.service.internal.NotificationRequests;
import kr.mujuthaek.api.notification.service.internal.PushDevice;
import kr.mujuthaek.api.notification.service.internal.Recipient;
import kr.mujuthaek.api.notification.service.internal.RecipientFinder;
import kr.mujuthaek.api.notification.service.internal.ReportAnsweredNotificationService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

/** 제보 답변 → REPORT_ANSWERED: 제보 종류별 대상·링크·문구, 답변 원문은 싣지 않음 (DB 없이). */
class ReportAnsweredNotificationServiceTest {

  static final String SECRET_REPLY = "010-1234-5678로 연락 주신 분, 고쳤어요";

  final NoticeQueryService notices = mock(NoticeQueryService.class);
  final BenefitQueryService benefits = mock(BenefitQueryService.class);
  final RecipientFinder finder = mock(RecipientFinder.class);
  final Outbox outbox = mock(Outbox.class);
  final InboxRepository inbox = mock(InboxRepository.class);
  final Clock clock = Clock.fixed(Instant.parse("2026-10-27T00:00:00Z"), ZoneId.of("Asia/Seoul"));
  final ReportAnsweredNotificationService service =
      new ReportAnsweredNotificationService(
          notices,
          benefits,
          finder,
          new NotificationRequests(
              outbox,
              ids ->
                  Map.of(
                      ids.iterator().next(),
                      List.of(new PushDevice("https://fcm.googleapis.com/fcm/send/x", "k", "a"))),
              inbox,
              clock));
  final UUID reportId = UUID.randomUUID();
  final UUID reporter = UUID.randomUUID();

  @BeforeEach
  void reporterHasPush() {
    when(finder.forReporter(reporter)).thenReturn(Recipient.push(reporter, true));
  }

  @Test
  void noticeReportGoesToTheReporterWithoutTheReplyText() {
    UUID notice = UUID.randomUUID();

    int sent =
        service.onAnswered(
            new NoticeReportAnswered(
                reportId, notice, reporter, "보증금", "FIXED", SECRET_REPLY, "강동 행복주택"));

    assertThat(sent).isEqualTo(1);
    Map<String, Object> payload = onlyPayload();
    assertThat(payload.get("type")).isEqualTo("REPORT_ANSWERED");
    assertThat(payload.get("dedupKey"))
        .isEqualTo("NOTICE:" + notice + ":ANSWERED:NOTICE:" + reportId);
    assertThat(payload.get("linkPath")).isEqualTo("/notices/" + notice);
    assertThat(payload.get("title")).isEqualTo("제보 답변: 강동 행복주택");
    assertThat(payload.get("body")).isEqualTo("제보하신 '보증금' 내용을 확인하고 고쳤어요.");
    assertThat(payload.toString()).doesNotContain("010-1234").doesNotContain(SECRET_REPLY);
    assertThat(((List<?>) payload.get("recipients"))).hasSize(1);
    InboxRepository.NewEntry entry = onlyInboxEntry();
    assertThat(entry.userId()).isEqualTo(reporter);
    assertThat(entry.body()).doesNotContain("010-1234");
    // 기기가 「떴어요·눌렀어요」를 알릴 수 있게 알림함 줄 ID를 요청에도 실어요
    assertThat(((Map<?, ?>) ((List<?>) payload.get("recipients")).getFirst()).get("inboxId"))
        .isEqualTo(entry.id());
  }

  @Test
  void generalReportAnswerStaysInTheInboxOnlyAndOpensMyReports() {
    int sent =
        service.onAnswered(
            new kr.mujuthaek.api.common.event.GeneralReportAnswered(
                reportId, reporter, "MISSING_NOTICE", "FIXED", SECRET_REPLY));

    // 가리킬 대상이 없어 알림 서버 요청(푸시·메일)은 만들지 않고 알림함에만 남겨요
    assertThat(sent).isZero();
    org.mockito.Mockito.verify(outbox, org.mockito.Mockito.never())
        .add(
            org.mockito.ArgumentMatchers.anyString(),
            org.mockito.ArgumentMatchers.anyInt(),
            org.mockito.ArgumentMatchers.any());
    InboxRepository.NewEntry entry = onlyInboxEntry();
    assertThat(entry.userId()).isEqualTo(reporter);
    assertThat(entry.targetType()).isNull();
    assertThat(entry.targetId()).isNull();
    assertThat(entry.linkPath()).isEqualTo("/me?tab=reports");
    assertThat(entry.title()).isEqualTo("제보 답변이 도착했어요");
    assertThat(entry.body()).doesNotContain(SECRET_REPLY);
  }

  @Test
  void areaReportUsesTheNoticeTitleAndTheMergedNotice() {
    UUID asked = UUID.randomUUID();
    UUID remaining = UUID.randomUUID();
    when(notices.findSummary(asked)).thenReturn(Optional.of(notice(remaining, "서리풀 아트타운")));

    service.onAnswered(
        new AreaReportAnswered(reportId, asked, reporter, "역까지 거리", "KEPT", SECRET_REPLY, null));

    Map<String, Object> payload = onlyPayload();
    assertThat(payload.get("dedupKey"))
        .isEqualTo("NOTICE:" + remaining + ":ANSWERED:AREA:" + reportId);
    assertThat(payload.get("linkPath")).isEqualTo("/notices/" + remaining);
    assertThat(payload.get("title")).isEqualTo("제보 답변: 서리풀 아트타운");
    assertThat(payload.get("body")).isEqualTo("제보하신 생활권 '역까지 거리' 내용을 확인했어요. 원문과 같아 그대로 두었어요.");
  }

  @Test
  void businessSpaceNoticeLinksToTheSpaceScreen() {
    UUID space = UUID.randomUUID();
    when(notices.findSummary(space))
        .thenReturn(Optional.of(notice(space, "BUSINESS_SPACE", "성수 창업 공간")));

    service.onAnswered(
        new NoticeReportAnswered(reportId, space, reporter, "임대료", "FIXED", SECRET_REPLY, null));

    assertThat(onlyPayload().get("linkPath")).isEqualTo("/business/spaces/" + space);
  }

  @Test
  void benefitReportLinksToTheBenefitFoundByRawPolicyId() {
    UUID raw = UUID.randomUUID();
    UUID benefit = UUID.randomUUID();
    when(benefits.findSummaryByRawPolicyId(raw)).thenReturn(Optional.of(benefit(benefit)));

    service.onAnswered(
        new BenefitReportAnswered(reportId, raw, reporter, "지원 금액", "FIXED", SECRET_REPLY, null));

    Map<String, Object> payload = onlyPayload();
    assertThat(payload.get("linkPath")).isEqualTo("/benefits/" + benefit);
    assertThat(payload.get("target")).isEqualTo(Map.of("type", "BENEFIT", "id", benefit));
    assertThat(payload.get("title")).isEqualTo("제보 답변: 청년 월세 지원");
  }

  @Test
  void programReportLinksToTheStartupSupport() {
    UUID program = UUID.randomUUID();
    when(notices.findPolicySummary(program))
        .thenReturn(
            Optional.of(
                new PolicySummary(
                    program,
                    2,
                    "STARTUP_SUPPORT",
                    "예비창업패키지",
                    null,
                    "APPLYING",
                    null,
                    null,
                    List.of(),
                    null,
                    null)));

    service.onAnswered(
        new ProgramReportAnswered(reportId, program, reporter, "지원 대상", "KEPT", "그대로", null));

    Map<String, Object> payload = onlyPayload();
    assertThat(payload.get("linkPath")).isEqualTo("/business/support/" + program);
    assertThat(payload.get("target")).isEqualTo(Map.of("type", "STARTUP_SUPPORT", "id", program));
    assertThat(payload.get("title")).isEqualTo("제보 답변: 예비창업패키지");
  }

  @Test
  void spaceRecruitmentReportLinksToTheSpace() {
    UUID space = UUID.randomUUID();
    when(notices.findPolicySummary(space))
        .thenReturn(
            Optional.of(
                new PolicySummary(
                    space,
                    1,
                    "SPACE_RECRUITMENT",
                    "창업센터 입주 모집",
                    null,
                    "APPLYING",
                    null,
                    null,
                    List.of(),
                    null,
                    null)));

    service.onAnswered(
        new ProgramReportAnswered(reportId, space, reporter, "모집 기간", "FIXED", "고쳤어요", null));

    Map<String, Object> payload = onlyPayload();
    assertThat(payload.get("linkPath")).isEqualTo("/business/spaces/" + space);
    assertThat(payload.get("target")).isEqualTo(Map.of("type", "SPACE_RECRUITMENT", "id", space));
  }

  @Test
  void benefitThatIsNotStoredIsNotAlerted() {
    when(benefits.findSummaryByRawPolicyId(any())).thenReturn(Optional.empty());

    assertThat(
            service.onAnswered(
                new BenefitReportAnswered(
                    reportId, UUID.randomUUID(), reporter, "금액", "FIXED", "고쳤어요", "제목")))
        .isZero();
    verify(outbox, never()).add(any(), anyInt(), any());
  }

  @SuppressWarnings("unchecked")
  private Map<String, Object> onlyPayload() {
    ArgumentCaptor<Object> payload = ArgumentCaptor.forClass(Object.class);
    verify(outbox).add(eq("notification.requested"), eq(1), payload.capture());
    return (Map<String, Object>) payload.getValue();
  }

  @SuppressWarnings("unchecked")
  private InboxRepository.NewEntry onlyInboxEntry() {
    ArgumentCaptor<List<InboxRepository.NewEntry>> entries = ArgumentCaptor.forClass(List.class);
    verify(inbox).addAll(entries.capture());
    assertThat(entries.getValue()).hasSize(1);
    return entries.getValue().getFirst();
  }

  private static NoticeSummary notice(UUID id, String title) {
    return notice(id, "HOUSING", title);
  }

  private static NoticeSummary notice(UUID id, String field, String title) {
    return new NoticeSummary(
        id, 1, field, title, null, null, "APPLYING", null, null, List.of(), false, "/", null);
  }

  private static BenefitSummary benefit(UUID id) {
    return new BenefitSummary(
        id,
        "BENEFIT",
        1,
        "청년 월세 지원",
        null,
        "OPEN",
        null,
        null,
        false,
        "NATIONWIDE",
        List.of(),
        null);
  }
}
