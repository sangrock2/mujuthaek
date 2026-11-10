package kr.mujuthaek.api.notification;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.stream.IntStream;
import kr.mujuthaek.api.benefit.service.BenefitQueryService;
import kr.mujuthaek.api.benefit.service.BenefitSummary;
import kr.mujuthaek.api.common.event.BenefitPublished;
import kr.mujuthaek.api.common.event.BenefitUpdated;
import kr.mujuthaek.api.common.messaging.Outbox;
import kr.mujuthaek.api.notification.repository.InboxRepository;
import kr.mujuthaek.api.notification.service.internal.BenefitNotificationService;
import kr.mujuthaek.api.notification.service.internal.NotificationRequests;
import kr.mujuthaek.api.notification.service.internal.Recipient;
import kr.mujuthaek.api.notification.service.internal.RecipientFinder;
import org.junit.jupiter.api.Test;

/** 받는 사람 나누기·숨긴 정책·알릴 부분 거르기 (DB 없이). */
class BenefitNotificationServiceTest {

  final BenefitQueryService benefits = mock(BenefitQueryService.class);
  final RecipientFinder finder = mock(RecipientFinder.class);
  final Outbox outbox = mock(Outbox.class);
  final Clock clock = Clock.fixed(Instant.parse("2026-10-25T00:00:00Z"), ZoneId.of("Asia/Seoul"));
  final BenefitNotificationService service =
      new BenefitNotificationService(
          benefits,
          finder,
          new NotificationRequests(outbox, ids -> Map.of(), mock(InboxRepository.class), clock),
          clock);
  final UUID id = UUID.randomUUID();

  @Test
  void moreThan500RecipientsAreSplit() {
    summary("OPEN", "BENEFIT");
    when(finder.forNewBenefit(any(), any(), any())).thenReturn(people(1_001));

    int sent =
        service.onPublished(new BenefitPublished(id, "BENEFIT", "SIDO", List.of("11"), "t", false));

    assertThat(sent).isEqualTo(3); // 500 + 500 + 1
    verify(outbox, times(3)).add(eq("notification.requested"), anyInt(), any());
  }

  @Test
  void hiddenOrMissingIsNotAlerted() {
    when(finder.forNewBenefit(any(), any(), any())).thenReturn(people(1));
    when(benefits.findSummary(id)).thenReturn(Optional.empty());
    assertThat(
            service.onPublished(new BenefitPublished(id, "BENEFIT", "SIDO", List.of(), "t", false)))
        .isZero();

    summary("HIDDEN", "BENEFIT");
    assertThat(service.onUpdated(new BenefitUpdated(id, "BENEFIT", 2, List.of("schedule"), false)))
        .isZero();
    verify(outbox, never()).add(any(), anyInt(), any());
  }

  @Test
  void noRecipientsMeansNoRequest() {
    summary("OPEN", "BENEFIT");
    when(finder.forFavorite(any(), any(), any())).thenReturn(List.of());

    assertThat(
            service.onUpdated(new BenefitUpdated(id, "BENEFIT", 2, List.of("conditions"), false)))
        .isZero();
    verify(outbox, never()).add(any(), anyInt(), any());
  }

  private void summary(String status, String field) {
    when(benefits.findSummary(id))
        .thenReturn(
            Optional.of(
                new BenefitSummary(
                    id,
                    field,
                    1,
                    "제목",
                    null,
                    status,
                    null,
                    LocalDate.of(2026, 11, 30),
                    false,
                    "SIDO",
                    List.of("11"),
                    null)));
  }

  private static List<Recipient> people(int n) {
    return IntStream.range(0, n)
        .mapToObj(i -> new Recipient(UUID.randomUUID(), "u" + i + "@example.com", false, true))
        .toList();
  }
}
