package kr.mujuthaek.api.notification;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.common.event.NoticePublished;
import kr.mujuthaek.api.common.event.NoticeUpdated;
import kr.mujuthaek.api.common.messaging.Outbox;
import kr.mujuthaek.api.notice.service.NoticeFollowUpSummary;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import kr.mujuthaek.api.notice.service.NoticeSummary;
import kr.mujuthaek.api.notification.repository.InboxRepository;
import kr.mujuthaek.api.notification.service.internal.NoticeNotificationService;
import kr.mujuthaek.api.notification.service.internal.NotificationRequests;
import kr.mujuthaek.api.notification.service.internal.Recipient;
import kr.mujuthaek.api.notification.service.internal.RecipientFinder;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/** 어떤 NoticeUpdated가 어떤 알림이 되는지, 숨긴·합친·마감 공고, 받는 사람 겹침 (DB 없이). */
class NoticeNotificationServiceTest {

  final NoticeQueryService notices = mock(NoticeQueryService.class);
  final RecipientFinder finder = mock(RecipientFinder.class);
  final Outbox outbox = mock(Outbox.class);
  final InboxRepository inbox = mock(InboxRepository.class);
  final Clock clock = Clock.fixed(Instant.parse("2026-10-25T00:00:00Z"), ZoneId.of("Asia/Seoul"));
  final NoticeNotificationService service =
      new NoticeNotificationService(
          notices, finder, new NotificationRequests(outbox, ids -> Map.of(), inbox, clock), clock);
  final UUID id = UUID.randomUUID();
  final Recipient me = new Recipient(UUID.randomUUID(), "me@example.com", false, true);

  @BeforeEach
  void favorites() {
    when(finder.forFavorite(eq("NOTICE"), eq(id), anyString())).thenReturn(List.of(me));
  }

  @Test
  void sourcesOnlyOrUnseenSectionsAreNotAlerted() {
    assertThat(service.onUpdated(updated("sources"))).isZero();
    assertThat(service.onUpdated(updated("guidance", "conditions", "heldItems", "judgment")))
        .isZero();
    assertThat(service.onUpdated(new NoticeUpdated(id, "HOUSING", null, false))).isZero();
    verifyNoInteractions(notices, outbox);
  }

  @Test
  void reprocessIsNotAlerted() {
    assertThat(service.onUpdated(new NoticeUpdated(id, "HOUSING", List.of("schedules"), true)))
        .isZero();
    assertThat(service.onPublished(published(true))).isZero();
    verifyNoInteractions(notices, outbox);
  }

  @Test
  void correctedBodyListsOnlyAlertedSectionsInOrder() {
    summary("APPLYING", 3);

    assertThat(service.onUpdated(updated("schedules", "guidance", "applicationWindows")))
        .isEqualTo(1);

    verify(outbox)
        .add(
            eq("notification.requested"),
            eq(1),
            argThat(
                (Map<String, Object> p) ->
                    p.get("type").equals("CORRECTED")
                        && p.get("dedupKey").equals("NOTICE:" + id + ":CORRECTED:3")
                        && p.get("body").equals("관심 공고의 일정, 접수 기간 내용이 바뀌었어요.")));
    verify(notices, never()).findLatestFollowUp(any());
  }

  @Test
  void followUpWithoutPostedDateLeavesTheDateOut() {
    summary("APPLYING", 1);
    UUID post = UUID.randomUUID();
    when(notices.findLatestFollowUp(id))
        .thenReturn(Optional.of(new NoticeFollowUpSummary(post, "당첨자 발표", null)));

    assertThat(service.onUpdated(updated("followUps"))).isEqualTo(1);

    verify(outbox)
        .add(
            eq("notification.requested"),
            eq(1),
            argThat(
                (Map<String, Object> p) ->
                    p.get("dedupKey").equals("NOTICE:" + id + ":FOLLOW_UP:" + post)
                        && p.get("body").equals("관심 공고에 '당첨자 발표' 안내가 올라왔어요.")));
  }

  @Test
  void followUpWithoutTitleSaysANewFollowUp() {
    summary("APPLYING", 1);
    when(notices.findLatestFollowUp(id))
        .thenReturn(
            Optional.of(
                new NoticeFollowUpSummary(UUID.randomUUID(), " ", LocalDate.of(2026, 10, 27))));

    service.onUpdated(updated("followUps"));

    verify(outbox)
        .add(
            eq("notification.requested"),
            eq(1),
            argThat(
                (Map<String, Object> p) ->
                    p.get("body").equals("관심 공고에 새 후속 안내 (10월 27일)가 올라왔어요.")));
  }

  @Test
  void followUpEventWithNoFollowUpFoundSendsNothing() {
    summary("APPLYING", 1);
    when(notices.findLatestFollowUp(id)).thenReturn(Optional.empty());

    assertThat(service.onUpdated(updated("followUps"))).isZero();
    verifyNoInteractions(outbox);
  }

  @Test
  void sectionsAndFollowUpsTogetherSendBoth() {
    summary("APPLYING", 2);
    when(notices.findLatestFollowUp(id))
        .thenReturn(
            Optional.of(
                new NoticeFollowUpSummary(UUID.randomUUID(), "서류 안내", LocalDate.of(2026, 10, 27))));

    assertThat(service.onUpdated(updated("eligibility", "followUps"))).isEqualTo(2);
    verify(outbox, times(2)).add(eq("notification.requested"), anyInt(), any());
  }

  @Test
  void hiddenNoticeIsNotAlerted() {
    when(notices.findSummary(id)).thenReturn(Optional.empty());

    assertThat(service.onUpdated(updated("schedules"))).isZero();
    assertThat(service.onPublished(published(false))).isZero();
    verifyNoInteractions(outbox);
  }

  @Test
  void publishedButAlreadyMergedOrClosedIsNotAlerted() {
    when(notices.findSummary(id))
        .thenReturn(
            Optional.of(notice(UUID.randomUUID(), "APPLYING", 1, LocalDate.of(2026, 10, 30))));
    assertThat(service.onPublished(published(false))).as("합쳐짐").isZero();

    summary("CLOSED", 1);
    assertThat(service.onPublished(published(false))).as("마감").isZero();
    verifyNoInteractions(outbox);
  }

  @Test
  void newNoticeCountsAPersonInBothListsOnceAndSaysAlwaysOpen() {
    when(notices.findSummary(id)).thenReturn(Optional.of(notice(id, "ALWAYS", 1, null)));
    Recipient other = new Recipient(UUID.randomUUID(), "other@example.com", true, true);
    when(finder.forNewNotice(eq("HOUSING"), eq(List.of("11650")), anyBoolean(), any()))
        .thenReturn(List.of(me, other));

    assertThat(service.onPublished(published(false))).isEqualTo(1);

    verify(outbox)
        .add(
            eq("notification.requested"),
            eq(1),
            argThat(
                (Map<String, Object> p) ->
                    ((List<?>) p.get("recipients")).size() == 2
                        && p.get("body").equals("관심 조건에 맞는 새 공고 소식이에요. SH공사 · 상시 모집")));
  }

  @Test
  void membersWithoutAnyChannelOnlyGetAnInboxEntry() {
    when(notices.findSummary(id)).thenReturn(Optional.of(notice(id, "APPLYING", 1, null)));
    Recipient silent = Recipient.push(UUID.randomUUID(), false); // 기기 없음
    Recipient off = new Recipient(UUID.randomUUID(), null, false, false); // 이 종류를 끔
    when(finder.forNewNotice(any(), any(), anyBoolean(), any())).thenReturn(List.of(silent, off));
    when(finder.forFavorite(eq("NOTICE"), eq(id), anyString())).thenReturn(List.of());

    assertThat(service.onPublished(published(false))).isZero();

    verify(inbox)
        .addAll(
            argThat(
                (List<InboxRepository.NewEntry> rows) ->
                    rows.size() == 2
                        && rows.stream()
                            .allMatch(r -> r.dedupKey().equals("NOTICE:" + id + ":NEW"))));
    verifyNoInteractions(outbox);
  }

  @Test
  void pastDeadlineIsLeftOutOfTheNewNoticeBody() {
    when(notices.findSummary(id))
        .thenReturn(Optional.of(notice(id, "UNKNOWN", 1, LocalDate.of(2026, 10, 24))));
    when(finder.forNewNotice(any(), any(), anyBoolean(), any())).thenReturn(List.of(me));

    service.onPublished(published(false));

    verify(outbox)
        .add(
            eq("notification.requested"),
            eq(1),
            argThat((Map<String, Object> p) -> p.get("body").equals("관심 조건에 맞는 새 공고 소식이에요. SH공사")));
  }

  private NoticeUpdated updated(String... changed) {
    return new NoticeUpdated(id, "HOUSING", List.of(changed), false);
  }

  private NoticePublished published(boolean reprocess) {
    return new NoticePublished(id, "HOUSING", "11650", List.of("11650"), false, "t", reprocess);
  }

  private void summary(String status, int version) {
    when(notices.findSummary(id))
        .thenReturn(Optional.of(notice(id, status, version, LocalDate.of(2026, 10, 30))));
  }

  private static NoticeSummary notice(UUID id, String status, int version, LocalDate applyEnd) {
    return new NoticeSummary(
        id,
        version,
        "HOUSING",
        "서리풀 청년아트타운",
        "SH공사",
        null,
        status,
        null,
        applyEnd,
        List.of("1165000000"),
        false,
        "/api/v1/notices/" + id,
        null);
  }
}
