package kr.mujuthaek.api.common.messaging;

import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.api.common.id.UuidV7;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.json.JsonMapper;

/**
 * 다른 서비스로 보낼 이벤트를 아웃박스(common.outbox)에 적어요. 실제 발송은 {@link OutboxRelay}가 해요.
 *
 * <p><b>저장과 같은 트랜잭션 안에서만</b> 부를 수 있어요 (트랜잭션이 없으면 예외). 그래서 저장이 되돌려지면 이벤트도 같이 사라지고, 저장이 되면 이벤트도 반드시
 * 남아요. RabbitMQ로 바로 보내면 "저장은 됐는데 보내기 전에 api가 죽어 이벤트가 사라지는" 일이 생겨요.
 *
 * <p>봉투 모양은 파이썬 쪽(libs/python-platform events.new_event)과 같아요: eventId(UUID
 * v7)·eventType·schemaVersion· occurredAt·producer(api)·payload. 라우팅 키는 eventType이에요.
 */
@Component
public class Outbox {

  static final String PRODUCER = "api";

  private final JdbcClient jdbc;
  private final JsonMapper json;
  private final Clock clock;

  public Outbox(JdbcClient jdbc, JsonMapper json, Clock clock) {
    this.jdbc = jdbc;
    this.json = json;
    this.clock = clock;
  }

  /**
   * @param eventType 이벤트 종류 = 라우팅 키 (예: notification.requested)
   * @param payload 봉투의 payload. record나 Map이면 돼요
   * @return 만든 eventId
   */
  @Transactional(propagation = Propagation.MANDATORY)
  public UUID add(String eventType, int schemaVersion, Object payload) {
    UUID eventId = UuidV7.next();
    Map<String, Object> envelope = new LinkedHashMap<>();
    envelope.put("eventId", eventId);
    envelope.put("eventType", eventType);
    envelope.put("schemaVersion", schemaVersion);
    envelope.put("occurredAt", Instant.now(clock).truncatedTo(ChronoUnit.MILLIS).toString());
    envelope.put("producer", PRODUCER);
    envelope.put("payload", payload);
    jdbc.sql(
            """
            insert into common.outbox (event_id, event_type, schema_version, payload)
            values (:id, :type, :version, cast(:payload as jsonb))
            """)
        .param("id", eventId)
        .param("type", eventType)
        .param("version", schemaVersion)
        .param("payload", json.writeValueAsString(envelope))
        .update();
    return eventId;
  }
}
