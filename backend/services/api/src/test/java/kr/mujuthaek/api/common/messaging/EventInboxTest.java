package kr.mujuthaek.api.common.messaging;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.TestDatabase;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.jdbc.core.JdbcTemplate;
import tools.jackson.databind.json.JsonMapper;

class EventInboxTest {

  record Sample(String name, int count) {}

  private final JdbcTemplate jdbc = new JdbcTemplate(TestDatabase.dataSource());
  private final EventInbox inbox = new EventInbox(JsonMapper.builder().build(), jdbc);
  private final List<Sample> handled = new ArrayList<>();

  @Test
  void handlesAnEventOnceAndRemembersIt() {
    UUID id = UUID.randomUUID();
    Message message =
        message(id, "sample.ready", 1, "{\"name\":\"강원\",\"count\":3,\"extra\":true}");

    inbox.handleOnce(message, "sample.ready", 1, Sample.class, handled::add);
    inbox.handleOnce(message, "sample.ready", 1, Sample.class, handled::add);

    assertThat(handled).containsExactly(new Sample("강원", 3));
    assertThat(
            jdbc.queryForObject(
                "select event_type from common.processed_events where event_id = ?",
                String.class,
                id))
        .isEqualTo("sample.ready");
  }

  @Test
  void failedHandlingIsNotRemembered_soItRunsAgain() {
    Message message = message(UUID.randomUUID(), "sample.ready", 1, "{\"name\":\"a\",\"count\":1}");

    assertThatThrownBy(
            () ->
                inbox.handleOnce(
                    message,
                    "sample.ready",
                    1,
                    Sample.class,
                    s -> {
                      throw new IllegalStateException("S3 연결 끊김");
                    }))
        .isInstanceOf(IllegalStateException.class);
    inbox.handleOnce(message, "sample.ready", 1, Sample.class, handled::add);

    assertThat(handled).hasSize(1);
  }

  @Test
  void unreadableOrUnexpectedEventsGoToTheDeadLetterQueueWithoutRetry() {
    Message notJson =
        new Message("not json".getBytes(StandardCharsets.UTF_8), new MessageProperties());
    Message otherType = message(UUID.randomUUID(), "raw.notice.collected", 1, "{}");
    Message otherVersion = message(UUID.randomUUID(), "sample.ready", 2, "{}");

    for (Message m : List.of(notJson, otherType, otherVersion)) {
      assertThatThrownBy(() -> inbox.handleOnce(m, "sample.ready", 1, Sample.class, handled::add))
          .isInstanceOf(AmqpRejectAndDontRequeueException.class);
    }
    assertThat(handled).isEmpty();
  }

  @Test
  void payloadOfTheWrongShapeIsRejected() {
    Message message = message(UUID.randomUUID(), "sample.ready", 1, "{\"count\":\"많음\"}");

    assertThatThrownBy(
            () -> inbox.handleOnce(message, "sample.ready", 1, Sample.class, handled::add))
        .isInstanceOf(AmqpRejectAndDontRequeueException.class);
  }

  private static Message message(UUID id, String type, int version, String payload) {
    String body =
        """
        {"eventId":"%s","eventType":"%s","schemaVersion":%d,"occurredAt":"2026-10-22T03:00:00Z",
         "producer":"collector","payload":%s}"""
            .formatted(id, type, version, payload);
    return new Message(body.getBytes(StandardCharsets.UTF_8), new MessageProperties());
  }
}
