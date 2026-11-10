package kr.mujuthaek.api.area.event;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

import java.nio.charset.StandardCharsets;
import java.util.UUID;
import kr.mujuthaek.api.TestDatabase;
import kr.mujuthaek.api.area.repository.AreaLoadQueue;
import kr.mujuthaek.api.area.service.AreaLoadWorker;
import kr.mujuthaek.api.common.messaging.EventInbox;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.jdbc.core.JdbcTemplate;
import tools.jackson.databind.json.JsonMapper;

class AreaSourceReadyListenerTest {

  private final JdbcTemplate jdbc = new JdbcTemplate(TestDatabase.dataSource());
  private final AreaLoadWorker worker = mock(AreaLoadWorker.class);
  private final AreaSourceReadyListener listener =
      new AreaSourceReadyListener(
          new EventInbox(JsonMapper.builder().build(), jdbc), new AreaLoadQueue(jdbc), worker);

  @BeforeEach
  void clean() {
    jdbc.update("delete from area.load_runs where source = 'STORES' and load_scope = '강원'");
  }

  @Test
  void queuesTheFileAndWakesTheWorker_withoutLoadingHere() {
    listener.on(message(UUID.randomUUID(), "STORES", "강원"));

    assertThat(statuses()).isEqualTo("PENDING");
    assertThat(
            jdbc.queryForObject(
                "select file_key || '|' || data_date from area.load_runs where load_scope = '강원'",
                String.class))
        .isEqualTo("area/STORES/2026-06-30/stores_gangwon.csv|2026-06-30");
    verify(worker).wake();
  }

  @Test
  void sameFileWhileWaiting_isNotQueuedTwice() {
    UUID id = UUID.randomUUID();
    listener.on(message(id, "STORES", "강원"));
    listener.on(message(id, "STORES", "강원"));

    assertThat(statuses()).isEqualTo("PENDING");
    verify(worker, times(1)).wake();
  }

  @Test
  void alreadyLoadedFile_isRecordedAsSkipped() {
    insert("SUCCEEDED");

    listener.on(message(UUID.randomUUID(), "STORES", "강원"));

    assertThat(statuses()).isEqualTo("SKIPPED,SUCCEEDED");
    verify(worker, never()).wake();
  }

  @Test
  void failedFileSentAgain_isQueuedAgain_evenWithTheSameEventId() {
    UUID id = UUID.randomUUID();
    insert("FAILED");
    jdbc.update(
        "insert into common.processed_events (event_id, event_type) values (?, 'area.source.ready')",
        id);

    listener.on(message(id, "STORES", "강원"));

    assertThat(statuses()).isEqualTo("FAILED,PENDING");
  }

  @Test
  void unknownSourceGoesStraightToTheDeadLetterQueue() {
    assertThatThrownBy(() -> listener.on(message(UUID.randomUUID(), "SUPERMARKET", "ALL")))
        .isInstanceOf(AmqpRejectAndDontRequeueException.class);
    verify(worker, never()).wake();
  }

  @Test
  void scopedSourceWithoutScope_goesStraightToTheDeadLetterQueue() {
    assertThatThrownBy(() -> listener.on(message(UUID.randomUUID(), "STORES", "")))
        .isInstanceOf(AmqpRejectAndDontRequeueException.class);
  }

  private String statuses() {
    return jdbc.queryForObject(
        "select string_agg(status, ',' order by status) from area.load_runs where load_scope = '강원'",
        String.class);
  }

  private void insert(String status) {
    jdbc.update(
        "insert into area.load_runs (source, load_scope, file_key, file_sha256, data_date, status)"
            + " values ('STORES', '강원', 'area/x.csv', ?, date '2026-06-30', ?)",
        "ab".repeat(32),
        status);
  }

  private static Message message(UUID id, String source, String scope) {
    String body =
        """
        {"eventId":"%s","eventType":"area.source.ready","schemaVersion":1,
         "occurredAt":"2026-10-22T03:00:00Z","producer":"collector",
         "payload":{"source":"%s","scope":"%s","s3Key":"area/STORES/2026-06-30/stores_gangwon.csv",
                    "sha256":"%s","dataDate":"2026-06-30","fileName":"원본.csv","rows":3}}"""
            .formatted(id, source, scope, "ab".repeat(32));
    return new Message(body.getBytes(StandardCharsets.UTF_8), new MessageProperties());
  }
}
