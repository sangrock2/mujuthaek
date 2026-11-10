package kr.mujuthaek.notification.outbox;

import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.notification.support.UuidV7;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.json.JsonMapper;

/**
 * 다른 서비스로 보낼 이벤트를 아웃박스(outbox)에 적어요. 실제 발송은 {@link OutboxRelay}가 해요 (api common.outbox와 같은 방식).
 *
 * <p><b>발송 결과를 남기는 트랜잭션 안에서만</b> 불러요. 결과가 되돌려지면 이벤트도 사라지고, 결과가 남으면 이벤트도 반드시 나가요. 봉투는 eventId(UUID
 * v7)·eventType·schemaVersion·occurredAt·producer(notification)·payload, 라우팅 키는 eventType이에요.
 */
@Component
public class Outbox {

  static final String PRODUCER = "notification";

  private final JdbcClient jdbc;
  private final JsonMapper json;
  private final Clock clock;

  public Outbox(JdbcClient jdbc, JsonMapper json, Clock clock) {
    this.jdbc = jdbc;
    this.json = json;
    this.clock = clock;
  }

  @Transactional(propagation = Propagation.MANDATORY)
  public UUID add(String eventType, int schemaVersion, Object payload) {
    UUID eventId = UuidV7.next(clock);
    Map<String, Object> envelope = new LinkedHashMap<>();
    envelope.put("eventId", eventId);
    envelope.put("eventType", eventType);
    envelope.put("schemaVersion", schemaVersion);
    envelope.put("occurredAt", Instant.now(clock).truncatedTo(ChronoUnit.MILLIS).toString());
    envelope.put("producer", PRODUCER);
    envelope.put("payload", payload);
    jdbc.sql(
            """
            insert into outbox (event_id, event_type, schema_version, payload)
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
