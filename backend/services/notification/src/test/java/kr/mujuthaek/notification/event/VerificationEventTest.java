package kr.mujuthaek.notification.event;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import kr.mujuthaek.notification.TestcontainersConfiguration;
import kr.mujuthaek.notification.delivery.DeliveryFlowTest;
import kr.mujuthaek.notification.delivery.DeliveryFlowTest.RecordingEmailSender;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

/** email.verification.requested를 받으면 인증 코드 메일을 바로 보내요. */
@SpringBootTest(properties = "notification.delivery.poll-enabled=false")
@Import({TestcontainersConfiguration.class, DeliveryFlowTest.Fakes.class})
class VerificationEventTest {

  @Autowired RabbitTemplate rabbit;
  @Autowired RecordingEmailSender email;

  @BeforeEach
  void clear() {
    email.sent.clear();
  }

  @Test
  void sendsCodeRightAway() throws Exception {
    String body =
        """
        {"eventId":"%s","eventType":"email.verification.requested","schemaVersion":1,
         "occurredAt":"2026-10-23T05:00:00Z","producer":"api",
         "payload":{"userId":"%s","email":"me@example.com","code":"123456",
                    "expiresAt":"2026-10-23T05:10:00Z"}}
        """
            .formatted(UUID.randomUUID(), UUID.randomUUID());
    MessageProperties props = new MessageProperties();
    props.setContentType(MessageProperties.CONTENT_TYPE_JSON);
    rabbit.send(
        EventQueueConfig.EXCHANGE,
        "email.verification.requested",
        new Message(body.getBytes(), props));

    Instant until = Instant.now().plus(Duration.ofSeconds(10));
    while (email.sent.isEmpty() && Instant.now().isBefore(until)) {
      Thread.sleep(100);
    }
    assertThat(email.sent).hasSize(1);
    assertThat(email.sent.getFirst().to()).isEqualTo("me@example.com");
    assertThat(email.sent.getFirst().subject()).isEqualTo("[무주택자들] 이메일 인증 코드 123456");
    assertThat(email.sent.getFirst().text()).contains("14:10까지"); // 한국 시간
  }
}
