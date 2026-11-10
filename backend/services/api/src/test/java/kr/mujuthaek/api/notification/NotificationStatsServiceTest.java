package kr.mujuthaek.api.notification;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.List;
import java.util.Optional;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.notification.client.NotificationServerClient;
import kr.mujuthaek.api.notification.repository.InboxRepository;
import kr.mujuthaek.api.notification.service.internal.NotificationStatsService;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

/** 관리자 알림 화면: 알림함 지표는 늘 주고, 알림 서버에 닿지 못하면 발송 결과만 비워요. */
class NotificationStatsServiceTest {

  final InboxRepository inbox = mock(InboxRepository.class);
  final NotificationServerClient server = mock(NotificationServerClient.class);
  final Instant now = Instant.parse("2026-10-28T03:00:00Z");
  final NotificationStatsService service =
      new NotificationStatsService(inbox, server, Clock.fixed(now, ZoneId.of("Asia/Seoul")));

  @Test
  void engagementByTypeWithDeliveryResults() {
    when(inbox.engagement(Instant.parse("2026-10-21T03:00:00Z")))
        .thenReturn(List.of(new InboxRepository.Engagement("DEADLINE_D1", 10, 6, 4, 3)));
    var delivery = JsonMapper.builder().build().readTree("{\"days\":7,\"byType\":[]}");
    when(server.deliveryStats(7)).thenReturn(Optional.of(delivery));

    var stats = service.stats(7);

    assertThat(stats.days()).isEqualTo(7);
    assertThat(stats.delivery()).isEqualTo(delivery);
    assertThat(stats.engagement())
        .singleElement()
        .satisfies(
            e -> {
              assertThat(e.type()).isEqualTo("DEADLINE_D1");
              assertThat(e.created()).isEqualTo(10);
              assertThat(e.shown()).isEqualTo(6);
              assertThat(e.read()).isEqualTo(4);
              assertThat(e.clicked()).isEqualTo(3);
            });
  }

  @Test
  void sameDaysIsReusedForAMinute() {
    when(inbox.engagement(Instant.parse("2026-10-21T03:00:00Z"))).thenReturn(List.of());
    when(server.deliveryStats(7)).thenReturn(Optional.empty());

    var first = service.stats(7);
    assertThat(service.stats(7)).isSameAs(first); // 1분 안: 알림함·알림 서버를 다시 묻지 않아요
    org.mockito.Mockito.verify(server, org.mockito.Mockito.times(1)).deliveryStats(7);
  }

  @Test
  void notificationServerDownStillShowsInboxNumbers() {
    when(inbox.engagement(Instant.parse("2026-10-27T03:00:00Z")))
        .thenReturn(List.of(new InboxRepository.Engagement("NEW_NOTICE", 2, 0, 1, 1)));
    when(server.deliveryStats(1)).thenReturn(Optional.empty());

    var stats = service.stats(1);

    assertThat(stats.delivery()).isNull();
    assertThat(stats.engagement()).hasSize(1);
  }

  @Test
  void daysOutsideTheInboxRetentionAreRejected() {
    assertThatThrownBy(() -> service.stats(0)).isInstanceOf(CustomException.class);
    assertThatThrownBy(() -> service.stats(91)).isInstanceOf(CustomException.class);
  }
}
