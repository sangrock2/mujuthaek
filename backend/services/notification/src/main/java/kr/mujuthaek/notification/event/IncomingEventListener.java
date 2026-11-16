package kr.mujuthaek.notification.event;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.UUID;
import kr.mujuthaek.notification.notification.NotificationRequest;
import kr.mujuthaek.notification.notification.NotificationService;
import kr.mujuthaek.notification.notification.UserDataCleaner;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * 이벤트를 받아 한 번만 처리해요. 같은 eventId가 다시 오면(재전송·중복 발행) 건너뛰어요.
 *
 * <p>처리한 이벤트 기록(processed_events)과 처리 결과는 한 트랜잭션이에요. 처리 중 오류가 나면 기록도 남지 않아요. 봉투가 깨진 메시지는 다시 시도해도
 * 같아서 실패 큐(.dlq)로 보내요.
 */
@Component
public class IncomingEventListener {

  private static final Logger log = LoggerFactory.getLogger(IncomingEventListener.class);

  /** 받는 봉투 버전. 바뀌면 새 버전을 받는 코드를 같이 넣어요. */
  static final int SCHEMA_VERSION = 1;

  /**
   * 이보다 오래된 알림 요청은 보내지 않고 버려요(처리 기록만 남겨요). 실패 큐에 오래 남은 메시지를 나중에 다시 넣으면, 탈퇴 기록(90일 보관)이 지워진 뒤라 탈퇴한
   * 사람에게 알림이 갈 수 있었어요(2026-11-16 보안 감사 L-14). 실패 큐 보관 기간(7일)과 같아요.
   */
  static final Duration MAX_REQUEST_AGE = Duration.ofDays(7);

  private final JsonMapper json;
  private final JdbcClient jdbc;
  private final NotificationService notifications;
  private final UserDataCleaner cleaner;
  private final Clock clock;

  public IncomingEventListener(
      JsonMapper json,
      JdbcClient jdbc,
      NotificationService notifications,
      UserDataCleaner cleaner,
      Clock clock) {
    this.json = json;
    this.jdbc = jdbc;
    this.notifications = notifications;
    this.cleaner = cleaner;
    this.clock = clock;
  }

  @RabbitListener(queues = EventQueueConfig.QUEUE)
  @Transactional
  public void onMessage(Message message) {
    Envelope event = parse(message.getBody());
    boolean first =
        jdbc.sql(
                    "insert into processed_events (event_id, event_type) values (:id, :type) on conflict do nothing")
                .param("id", event.eventId())
                .param("type", event.eventType())
                .update()
            == 1;
    if (!first) {
      log.debug("이미 처리한 이벤트: eventId={}, eventType={}", event.eventId(), event.eventType());
      return;
    }
    switch (event.eventType()) {
      case "notification.requested" -> {
        NotificationRequest request = payload(event, NotificationRequest.class);
        if (stale(event)) {
          log.warn(
              "오래된 알림 요청이라 보내지 않아요: eventId={}, occurredAt={}",
              event.eventId(),
              event.occurredAt());
          return;
        }
        int created = notifications.handle(request);
        log.info("알림 요청 처리: eventId={}, 새 발송 줄={}", event.eventId(), created);
      }
      case "user.withdrawn" -> {
        cleaner.delete(payload(event, Withdrawn.class).userId());
        log.info("탈퇴 회원 발송 기록 지움: eventId={}", event.eventId());
      }
      default -> throw new IllegalStateException("받는 종류인데 처리 코드가 없어요: " + event.eventType());
    }
  }

  /** 일어난 시각이 {@link #MAX_REQUEST_AGE}보다 오래됐으면 true. 시각이 없거나 읽을 수 없으면 false(예전 발행자) */
  private boolean stale(Envelope event) {
    return event.occurredAt() != null
        && event.occurredAt().isBefore(clock.instant().minus(MAX_REQUEST_AGE));
  }

  /** payload가 계약과 다르면 다시 받아도 같아서 실패 큐로 보내요 */
  private <T> T payload(Envelope event, Class<T> type) {
    try {
      T value = json.treeToValue(event.payload(), type);
      if (value == null) {
        throw new IllegalArgumentException("payload가 없어요");
      }
      if (value instanceof NotificationRequest request) {
        request.validate();
      }
      if (value instanceof Withdrawn withdrawn && withdrawn.userId() == null) {
        throw new IllegalArgumentException("userId가 없어요");
      }
      return value;
    } catch (JacksonException | IllegalArgumentException e) {
      throw new AmqpRejectAndDontRequeueException(
          "payload를 읽지 못했어요: eventId=" + event.eventId() + ", " + e.getMessage(), e);
    }
  }

  private Envelope parse(byte[] body) {
    try {
      JsonNode root = json.readTree(body);
      UUID eventId = UUID.fromString(root.path("eventId").asString());
      String eventType = root.path("eventType").asString();
      if (eventType.isBlank()) {
        throw new IllegalArgumentException("eventType이 없어요");
      }
      // 모르는 종류·버전을 처리했다고 기록하면 모양이 다른 이벤트가 조용히 사라져요. 실패 큐로 보내서 사람이 보게 해요
      if (!EventQueueConfig.ROUTING_KEYS.contains(eventType)) {
        throw new IllegalArgumentException("받지 않는 이벤트 종류예요: " + eventType);
      }
      int schemaVersion = root.path("schemaVersion").asInt(0);
      if (schemaVersion != SCHEMA_VERSION) {
        throw new IllegalArgumentException(
            "받을 수 없는 봉투 버전이에요: "
                + eventType
                + " v"
                + schemaVersion
                + " (기대: v"
                + SCHEMA_VERSION
                + ")");
      }
      return new Envelope(eventId, eventType, occurredAt(root), root.path("payload"));
    } catch (JacksonException | IllegalArgumentException e) {
      throw new AmqpRejectAndDontRequeueException("이벤트 봉투를 읽지 못했어요: " + e.getMessage(), e);
    }
  }

  private static Instant occurredAt(JsonNode root) {
    String value = root.path("occurredAt").asString();
    if (value.isBlank()) {
      return null;
    }
    try {
      return Instant.parse(value);
    } catch (DateTimeParseException e) {
      return null;
    }
  }

  private record Envelope(UUID eventId, String eventType, Instant occurredAt, JsonNode payload) {}

  private record Withdrawn(UUID userId) {}
}
