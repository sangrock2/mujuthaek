package kr.mujuthaek.api.common.messaging;

import java.nio.charset.StandardCharsets;
import java.util.function.BiConsumer;
import java.util.function.Consumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Message;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.json.JsonMapper;

/**
 * RabbitMQ로 받은 이벤트를 봉투에서 꺼내 한 번만 처리해요. 모든 모듈의 수신기가 같이 써요.
 *
 * <ol>
 *   <li>봉투를 읽어요. JSON이 아니거나 이벤트 종류·버전이 다르면 다시 해도 같으니 재시도 없이 실패 큐로 보내요
 *   <li>common.processed_events에 있는 eventId면 처리하지 않아요
 *   <li>처리가 끝나면 eventId를 기록해요. 처리 중 예외가 나면 기록하지 않아서, 다시 받으면 다시 처리해요
 * </ol>
 *
 * <p>처리와 기록이 한 트랜잭션이 아니어서, 처리 뒤 기록 전에 멈추면 같은 이벤트를 한 번 더 처리할 수 있어요. 그래서 처리 쪽도 같은 이벤트를 두 번 받아도 결과가
 * 같아야 해요.
 */
@Component
public class EventInbox {

  private static final Logger log = LoggerFactory.getLogger(EventInbox.class);

  private final JsonMapper json;
  private final JdbcTemplate jdbc;

  public EventInbox(JsonMapper json, JdbcTemplate jdbc) {
    this.json = json;
    this.jdbc = jdbc;
  }

  /**
   * @param eventType 받을 이벤트 종류 (예: area.source.ready)
   * @param schemaVersion 받을 봉투 버전
   * @param payloadType payload를 바꿀 record. record에 없는 칸(기록용 칸 등)은 무시해요
   */
  public <T> void handleOnce(
      Message message,
      String eventType,
      int schemaVersion,
      Class<T> payloadType,
      Consumer<T> handler) {
    handleOnceWithEnvelope(
        message,
        eventType,
        schemaVersion,
        payloadType,
        (envelope, payload) -> handler.accept(payload));
  }

  /** handleOnce와 같고, 처리할 때 봉투(eventId 등)도 넘겨줘요. */
  public <T> void handleOnceWithEnvelope(
      Message message,
      String eventType,
      int schemaVersion,
      Class<T> payloadType,
      BiConsumer<EventEnvelope, T> handler) {
    EventEnvelope envelope = readChecked(message, eventType, schemaVersion);
    if (alreadyProcessed(envelope)) {
      log.info("이미 처리한 이벤트라 건너뛰어요: {} {}", envelope.eventType(), envelope.eventId());
      return;
    }
    T payload = payload(envelope, payloadType);
    handler.accept(envelope, payload);
    markProcessed(envelope);
  }

  /**
   * 봉투를 읽어 payload만 돌려줘요. 처리 기록(processed_events)은 보지도 남기지도 않아요 — 받는 쪽이 따로 거를 때 써요 (예: area 적재는 같은
   * 파일이면 eventId가 같아서, 실패한 파일을 다시 올려도 처리되게 파일 기준으로 걸러요). 읽지 못하면 handleOnce와 같이 실패 큐로 보내요.
   */
  public <T> T readPayload(
      Message message, String eventType, int schemaVersion, Class<T> payloadType) {
    return payload(readChecked(message, eventType, schemaVersion), payloadType);
  }

  private EventEnvelope readChecked(Message message, String eventType, int schemaVersion) {
    EventEnvelope envelope = read(message);
    if (!eventType.equals(envelope.eventType()) || envelope.schemaVersion() != schemaVersion) {
      throw reject(
          "받을 수 없는 이벤트예요: "
              + envelope.eventType()
              + " v"
              + envelope.schemaVersion()
              + " (기대: "
              + eventType
              + " v"
              + schemaVersion
              + ")",
          null);
    }
    return envelope;
  }

  EventEnvelope read(Message message) {
    try {
      EventEnvelope envelope =
          json.readValue(
              new String(message.getBody(), StandardCharsets.UTF_8), EventEnvelope.class);
      if (envelope.eventId() == null
          || envelope.eventType() == null
          || envelope.payload() == null) {
        throw reject("이벤트 봉투에 eventId·eventType·payload가 없어요", null);
      }
      return envelope;
    } catch (JacksonException e) {
      throw reject("이벤트 봉투를 읽지 못했어요", e);
    }
  }

  private <T> T payload(EventEnvelope envelope, Class<T> type) {
    try {
      return json.treeToValue(envelope.payload(), type);
    } catch (JacksonException e) {
      throw reject("payload가 " + type.getSimpleName() + " 모양이 아니에요: " + envelope.eventId(), e);
    }
  }

  boolean alreadyProcessed(EventEnvelope envelope) {
    Integer found =
        jdbc.query(
            "select 1 from common.processed_events where event_id = ?",
            rs -> rs.next() ? 1 : null,
            envelope.eventId());
    return found != null;
  }

  void markProcessed(EventEnvelope envelope) {
    jdbc.update(
        "insert into common.processed_events (event_id, event_type) values (?, ?) on conflict do nothing",
        envelope.eventId(),
        envelope.eventType());
  }

  /** 다시 해도 같은 실패. 메시지 값(개인 정보가 있을 수 있음)은 넣지 않아요. */
  private static AmqpRejectAndDontRequeueException reject(String why, Throwable cause) {
    return new AmqpRejectAndDontRequeueException(why, cause);
  }
}
