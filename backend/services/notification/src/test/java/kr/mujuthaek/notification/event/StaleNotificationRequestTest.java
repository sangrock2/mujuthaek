package kr.mujuthaek.notification.event;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.RETURNS_DEEP_STUBS;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.UUID;
import kr.mujuthaek.notification.notification.NotificationService;
import kr.mujuthaek.notification.notification.UserDataCleaner;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.jdbc.core.simple.JdbcClient;
import tools.jackson.databind.json.JsonMapper;

/**
 * 보안 감사 L-14: 실패 큐에 오래 남은 알림 요청을 나중에 다시 넣으면, 탈퇴 기록(90일 보관)이 지워진 뒤라 탈퇴한 사람에게 알림이 갈 수 있었어요. 7일보다 오래된
 * 요청은 보내지 않아요.
 */
class StaleNotificationRequestTest {

  private static final Instant NOW = Instant.parse("2026-11-16T01:00:00Z");

  private final JdbcClient jdbc = mock(JdbcClient.class, RETURNS_DEEP_STUBS);
  private final NotificationService notifications = mock(NotificationService.class);
  private final IncomingEventListener listener =
      new IncomingEventListener(
          JsonMapper.builder().build(),
          jdbc,
          notifications,
          mock(UserDataCleaner.class),
          Clock.fixed(NOW, ZoneOffset.UTC));

  StaleNotificationRequestTest() {
    when(jdbc.sql(anyString()).param(anyString(), any()).param(anyString(), any()).update())
        .thenReturn(1);
  }

  private static Message request(Instant occurredAt) {
    UUID id = UUID.randomUUID();
    String body =
        """
        {"eventId":"%s","eventType":"notification.requested","schemaVersion":1,"occurredAt":"%s",
         "producer":"api","payload":{"type":"DEADLINE_D1","dedupKey":"NOTICE:%s:D1:2026-11-17",
         "target":{"type":"NOTICE","id":"%s"},"title":"내일 마감","body":"관심 공고가 내일 마감돼요.",
         "linkPath":"/notices/%s",
         "recipients":[{"userId":"%s","email":null,"quietEnabled":false}]}}
        """
            .formatted(id, occurredAt, id, id, id, UUID.randomUUID());
    return new Message(body.getBytes(StandardCharsets.UTF_8), new MessageProperties());
  }

  @Test
  void requestsOlderThanSevenDaysAreDroppedWithoutSending() {
    listener.onMessage(request(NOW.minus(Duration.ofDays(8))));
    verify(notifications, never()).handle(any());
  }

  @Test
  void recentRequestsAreSent() {
    listener.onMessage(request(NOW.minus(Duration.ofHours(1))));
    listener.onMessage(request(NOW.minus(Duration.ofDays(6))));
    verify(notifications, times(2)).handle(any());
  }

  @Test
  void missingInvalidOrFutureTimeCannotBypassTheReplayWindow() {
    String original = new String(request(NOW).getBody(), StandardCharsets.UTF_8);
    for (String body :
        new String[] {
          original.replace("\"occurredAt\":\"" + NOW + "\",", ""),
          original.replace(NOW.toString(), "not-a-time"),
          original.replace(NOW.toString(), NOW.plus(Duration.ofDays(90)).toString())
        }) {
      assertThatThrownBy(
              () ->
                  listener.onMessage(
                      new Message(body.getBytes(StandardCharsets.UTF_8), new MessageProperties())))
          .isInstanceOf(AmqpRejectAndDontRequeueException.class);
    }
    verify(notifications, never()).handle(any());
  }
}
