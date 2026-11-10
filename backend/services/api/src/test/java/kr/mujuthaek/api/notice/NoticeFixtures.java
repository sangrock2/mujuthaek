package kr.mujuthaek.api.notice;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;
import kr.mujuthaek.api.notice.mapper.NoticeProjection;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;

/**
 * notice 테스트용 extraction.completed payload. 계약 예시(contracts/examples/extraction.completed.json)를 바꿔
 * 써요.
 */
public final class NoticeFixtures {

  public static final JsonMapper JSON = JsonMapper.builder().build();

  private NoticeFixtures() {}

  /** 새 원본(rawPostId)의 모집공고 payload. */
  public static ObjectNode payload(UUID rawPostId, int rawVersion) {
    ObjectNode p = (ObjectNode) example().get("payload");
    p.put("rawPostId", rawPostId.toString());
    p.put("rawVersion", rawVersion);
    ObjectNode input = (ObjectNode) p.get("notice").get("input"); // 상세의 수신 정보도 같은 원본이어야 해요(계약 검사)
    input.put("rawPostId", rawPostId.toString());
    input.put("rawVersion", rawVersion);
    ObjectNode ref = (ObjectNode) p.get("notice").get("sourceReferences").get(0);
    ref.put("rawPostId", rawPostId.toString());
    ref.put("rawVersion", rawVersion);
    return p;
  }

  /** 정정공고 payload: 다른 원본이 original을 가리켜요. */
  public static ObjectNode correction(UUID rawPostId, UUID original) {
    ObjectNode p = payload(rawPostId, 1);
    ObjectNode ref = (ObjectNode) p.get("notice").get("sourceReferences").get(0);
    ref.put("kind", "CORRECTION");
    ref.put("supersedesPostId", original.toString());
    return p;
  }

  /** payload를 extraction.completed 봉투 글자로 감싸요 (eventId는 새로). */
  public static String envelope(ObjectNode payload) {
    ObjectNode envelope = JSON.createObjectNode();
    envelope.put("eventId", UUID.randomUUID().toString());
    envelope.put("eventType", "extraction.completed");
    envelope.put("schemaVersion", 1);
    envelope.put("occurredAt", "2026-10-22T00:00:00Z");
    envelope.put("producer", "extraction");
    envelope.set("payload", payload);
    return JSON.writeValueAsString(envelope);
  }

  /**
   * 공고 전체 접수 일정을 바꿔요(날짜만, 모르면 null). 원문 일정을 바꾸고 목록용 칸(schedule·applicationWindows)은 계약대로 원문 일정에서 다시
   * 만들어요.
   */
  public static void schedule(ObjectNode p, String start, String end) {
    ObjectNode application = (ObjectNode) p.get("notice").get("schedules").get(0);
    day(application, "startsAt", start);
    day(application, "endsAt", end);
    application.put(
        "endStatus", end == null ? "NOT_IN_SOURCE" : "FIXED"); // 계약: FIXED면 endsAt이 있어야 해요
    project(p);
  }

  /** 판정 틀을 이 payload와 같은 원본 글·버전으로 맞춰 넣어요 (계약: 틀의 rawPostId·rawVersion = payload의 것). */
  public static void judgment(ObjectNode p, JsonNode frame) {
    ObjectNode copy = (ObjectNode) frame.deepCopy();
    copy.set("rawPostId", p.get("rawPostId"));
    copy.set("rawVersion", p.get("rawVersion"));
    p.set("judgment", copy);
  }

  /** 모든 위치의 지역을 시군구 5자리로 바꾸고 payload의 지역 코드를 계약대로 다시 만들어요. */
  public static void region(ObjectNode p, String sigungu) {
    for (JsonNode location : p.get("notice").get("locations")) {
      ((ObjectNode) location).put("regionCode", sigungu + "00000");
    }
    p.put("regionCode", NoticeProjection.regionCode(p.get("notice")));
  }

  /** 목록용 칸(schedule·applicationWindows)을 원문 일정에서 다시 만들어요. */
  public static void project(ObjectNode p) {
    boolean approved = "APPROVED".equals(p.path("reviewStatus").asString());
    p.set("schedule", NoticeProjection.schedule(p.get("notice"), approved));
    p.set("applicationWindows", NoticeProjection.windows(p.get("notice"), approved));
  }

  private static void day(ObjectNode schedule, String name, String value) {
    if (value == null) {
      schedule.putNull(name);
    } else {
      schedule.putObject(name).put("precision", "DAY").put("value", value);
    }
  }

  public static ObjectNode followUp(UUID rawPostId, UUID original) {
    ObjectNode p = correction(rawPostId, original);
    ((ObjectNode) p.get("notice").get("sourceReferences").get(0)).put("kind", "FOLLOW_UP");
    return p;
  }

  private static ObjectNode example() {
    try {
      Path root = Path.of("").toAbsolutePath();
      while (!Files.isDirectory(root.resolve("contracts"))) {
        root = root.getParent();
      }
      return (ObjectNode)
          JSON.readTree(
              Files.readString(root.resolve("contracts/examples/extraction.completed.json")));
    } catch (java.io.IOException e) {
      throw new java.io.UncheckedIOException(e);
    }
  }
}
