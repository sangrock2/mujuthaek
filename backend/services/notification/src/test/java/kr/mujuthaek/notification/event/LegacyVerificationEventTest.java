package kr.mujuthaek.notification.event;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;

import java.nio.charset.StandardCharsets;
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
 * 보안 감사 M-8: 예전 인증 코드 이벤트(email.verification.requested)는 api가 더 보내지 않는데 받는 쪽이 남아 있어, MQ에 쓸 수 있는 누구나
 * 동의·횟수 제한 없이 아무 주소로 공식 메일을 보낼 수 있었어요. 이제 처리하지 않고 실패 큐로 보내요.
 */
class LegacyVerificationEventTest {

  @Test
  void legacyVerificationCodeEventIsRejectedWithoutSendingOrRecording() {
    var jdbc = mock(JdbcClient.class);
    var notifications = mock(NotificationService.class);
    var cleaner = mock(UserDataCleaner.class);
    var listener =
        new IncomingEventListener(
            JsonMapper.builder().build(),
            jdbc,
            notifications,
            cleaner,
            java.time.Clock.systemUTC());
    String body =
        """
        {"eventId":"%s","eventType":"email.verification.requested","schemaVersion":1,
         "payload":{"userId":"%s","email":"victim@example.com","code":"123456",
                    "expiresAt":"2026-11-16T05:10:00Z"}}
        """
            .formatted(UUID.randomUUID(), UUID.randomUUID());

    assertThatThrownBy(
            () ->
                listener.onMessage(
                    new Message(body.getBytes(StandardCharsets.UTF_8), new MessageProperties())))
        .isInstanceOf(AmqpRejectAndDontRequeueException.class);
    verifyNoInteractions(jdbc, notifications, cleaner);
    assertThat(EventQueueConfig.ROUTING_KEYS).doesNotContain("email.verification.requested");
  }
}
