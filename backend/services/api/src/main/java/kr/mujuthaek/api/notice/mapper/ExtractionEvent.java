package kr.mujuthaek.api.notice.mapper;

import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.UUID;
import kr.mujuthaek.api.notice.domain.ReviewStatus;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.JsonNodeFactory;
import tools.jackson.databind.node.ObjectNode;

/**
 * extraction.completed 이벤트 한 건에서 notice가 쓰는 값 (contracts/events/extraction.completed.v1.json).
 *
 * @param notice 상세 화면용 추출 공고(payload.notice). IN_REVIEW에서만 생략할 수 있어요
 * @param payload 받은 payload 전체 (수신 기록에 그대로 보관)
 */
public record ExtractionEvent(
    UUID eventId,
    UUID rawPostId,
    int rawVersion,
    String field,
    String title,
    ReviewStatus reviewStatus,
    boolean reprocess,
    String regionCode,
    LocalDate applyStartOn,
    LocalDate applyEndOn,
    JsonNode notice,
    JsonNode conditions,
    JsonNode heldItems,
    JsonNode applicationWindows,
    JsonNode payload) {

  public static final String EVENT_TYPE = "extraction.completed";

  /** 판정 틀(payload.judgment, 판정 담당이 정한 형식 그대로). 칸이 없거나 null이면 null. */
  public JsonNode judgment() {
    JsonNode frame = payload == null ? null : payload.path("judgment");
    return frame != null && frame.isObject() ? frame : null;
  }

  /** 이 코드가 읽는 이벤트 형식 버전 (계약 schemaVersion const). 다른 버전은 칸 뜻이 달라질 수 있어 받지 않아요. */
  public static final int SCHEMA_VERSION = 1;

  /** 계약에 맞지 않는 이벤트. 다시 받아도 같은 결과라 실패 큐로 보내요. */
  public static class InvalidEventException extends RuntimeException {
    public InvalidEventException(String message) {
      super(message);
    }
  }

  /** 봉투와 payload에서 값을 꺼내요. 필수 칸이 없거나 형식이 틀리면 InvalidEventException. */
  public static ExtractionEvent from(JsonNode envelope) {
    NoticeContract.validate(envelope);
    if (!EVENT_TYPE.equals(text(envelope, "eventType"))) {
      throw new InvalidEventException("eventType이 " + EVENT_TYPE + "가 아니에요");
    }
    JsonNode schemaVersion = envelope.path("schemaVersion");
    if (!schemaVersion.isNumber() || schemaVersion.asInt() != SCHEMA_VERSION) {
      throw new InvalidEventException("schemaVersion이 " + SCHEMA_VERSION + "이 아니에요");
    }
    JsonNode payload = envelope.path("payload");
    if (!payload.isObject()) {
      throw new InvalidEventException("payload가 없어요");
    }
    JsonNode schedule = payload.path("schedule");
    JsonNode notice = payload.path("notice");
    boolean approved = "APPROVED".equals(payload.path("reviewStatus").asString());
    if (notice.isObject() && !payload.has("schedule")) {
      schedule = NoticeProjection.schedule(notice, approved);
    }
    JsonNode heldItems = array(payload, "heldItems");
    if (notice.isObject() && !heldItems.equals(array(notice.path("quality"), "heldItems"))) {
      // 계약 EVENT_HELD_ITEMS_CONFLICT: 목록·판정(payload)과 상세 화면(notice)의 보류 범위가 달라지면 안 돼요
      throw new InvalidEventException("payload.heldItems와 notice.quality.heldItems가 달라요");
    }
    return new ExtractionEvent(
        uuid(envelope, "eventId"),
        uuid(payload, "rawPostId"),
        positiveInt(payload, "rawVersion"),
        required(payload, "field"),
        required(payload, "title"),
        reviewStatus(payload),
        payload.path("reprocess").asBoolean(false),
        text(payload, "regionCode"),
        date(schedule, "applyStartOn"),
        date(schedule, "applyEndOn"),
        notice.isObject() ? notice : null,
        conditions(payload, notice),
        heldItems,
        notice.isObject() && !payload.has("applicationWindows")
            ? NoticeProjection.windows(notice, approved)
            : array(payload, "applicationWindows"),
        payload);
  }

  /** 수신 기록에 보관한 payload로 다시 만들어요 (기다리던 정정 공고를 나중에 반영할 때). */
  public static ExtractionEvent fromStored(UUID eventId, JsonNode payload) {
    ObjectNode envelope = JsonNodeFactory.instance.objectNode();
    envelope.put("eventId", eventId.toString());
    envelope.put("eventType", EVENT_TYPE);
    envelope.put("schemaVersion", SCHEMA_VERSION); // 보관한 payload는 받을 때 이 버전으로 검사를 통과한 것
    envelope.put("producer", "extraction");
    envelope.put("occurredAt", java.time.Instant.EPOCH.toString()); // 저장 payload 재검사에만 쓰는 내부 봉투
    envelope.set("payload", payload);
    return from(envelope);
  }

  /** 이전 v1의 조건에는 scope가 없어요. 상세에서 정확히 복원하고 판정 모듈에도 전달해요. */
  private static JsonNode conditions(JsonNode payload, JsonNode notice) {
    JsonNode result = payload.path("conditions").deepCopy();
    if (notice.isObject()) {
      for (int i = 0; i < result.size(); i++) {
        if (!result.get(i).has("scope")) {
          ((ObjectNode) result.get(i))
              .set("scope", notice.path("eligibility").get(i).path("scope"));
        }
      }
    }
    return result;
  }

  private static String text(JsonNode node, String name) {
    JsonNode value = node.path(name);
    return value.isString() ? value.asString() : null;
  }

  private static String required(JsonNode node, String name) {
    String value = text(node, name);
    if (value == null || value.isBlank()) {
      throw new InvalidEventException(name + "가 없어요");
    }
    return value;
  }

  private static UUID uuid(JsonNode node, String name) {
    try {
      return UUID.fromString(required(node, name));
    } catch (IllegalArgumentException e) {
      throw new InvalidEventException(name + "가 UUID가 아니에요");
    }
  }

  private static int positiveInt(JsonNode node, String name) {
    JsonNode value = node.path(name);
    if (!value.isNumber() || value.asInt() < 1) {
      throw new InvalidEventException(name + "는 1 이상의 정수여야 해요");
    }
    return value.asInt();
  }

  private static ReviewStatus reviewStatus(JsonNode payload) {
    try {
      return ReviewStatus.valueOf(required(payload, "reviewStatus"));
    } catch (IllegalArgumentException e) {
      throw new InvalidEventException("reviewStatus 값이 올바르지 않아요");
    }
  }

  private static LocalDate date(JsonNode node, String name) {
    String value = text(node, name);
    if (value == null) {
      return null;
    }
    try {
      return LocalDate.parse(value);
    } catch (DateTimeParseException e) {
      throw new InvalidEventException(name + "가 날짜가 아니에요");
    }
  }

  /** 배열 칸. 없으면 빈 배열로 봐요(conditions는 계약상 필수라 없으면 오류). */
  private static JsonNode array(JsonNode node, String name) {
    JsonNode value = node.path(name);
    if (value.isArray()) {
      return value;
    }
    if ("conditions".equals(name)) {
      throw new InvalidEventException("conditions가 없어요");
    }
    return JsonNodeFactory.instance.arrayNode();
  }
}
