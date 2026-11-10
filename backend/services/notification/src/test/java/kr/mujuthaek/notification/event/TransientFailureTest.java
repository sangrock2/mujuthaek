package kr.mujuthaek.notification.event;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;

import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import kr.mujuthaek.notification.TestcontainersConfiguration;
import kr.mujuthaek.notification.delivery.DeliveryRepository;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

/** 처리 중 잠깐 생긴 오류(DB 끊김 등)로는 메시지를 실패 큐로 버리지 않고 다시 처리해요. */
@SpringBootTest(properties = "notification.delivery.poll-enabled=false")
@Import(TestcontainersConfiguration.class)
class TransientFailureTest {

  @Autowired RabbitTemplate rabbit;
  @Autowired JdbcClient jdbc;
  @MockitoSpyBean DeliveryRepository deliveries;

  @Test
  void temporaryErrorIsRetriedNotDeadLettered() throws Exception {
    // 첫 번째 처리만 실패 (DB가 잠깐 끊긴 것처럼), 그다음은 정상
    doThrow(new org.springframework.dao.TransientDataAccessResourceException("DB 잠깐 끊김"))
        .doCallRealMethod()
        .when(deliveries)
        .insert(any());
    UUID eventId = UUID.randomUUID();
    String body =
        """
        {"eventId":"%s","eventType":"notification.requested","schemaVersion":1,
         "occurredAt":"2026-10-24T00:00:00Z","producer":"api",
         "payload":{"type":"CORRECTED","dedupKey":"NOTICE:R:CORRECTED:2",
          "target":{"type":"NOTICE","id":"%s"},"title":"정정: 재시도","body":"본문",
          "linkPath":"/notices/r","recipients":[{"userId":"%s","email":"me@example.com",
          "quietEnabled":false}]}}
        """
            .formatted(eventId, UUID.randomUUID(), UUID.randomUUID());
    MessageProperties props = new MessageProperties();
    props.setContentType(MessageProperties.CONTENT_TYPE_JSON);
    rabbit.send(
        EventQueueConfig.EXCHANGE, "notification.requested", new Message(body.getBytes(), props));

    Instant until = Instant.now().plus(Duration.ofSeconds(20));
    while (processed(eventId) == 0 && Instant.now().isBefore(until)) {
      Thread.sleep(200);
    }
    assertThat(processed(eventId)).as("다시 처리돼서 기록이 남아야 해요").isEqualTo(1);
    assertThat(rabbit.receive(EventQueueConfig.DLQ, 500)).as("실패 큐로 가면 안 돼요").isNull();
  }

  private long processed(UUID eventId) {
    return jdbc.sql("select count(*) from processed_events where event_id = :id")
        .param("id", eventId)
        .query(Long.class)
        .single();
  }
}
