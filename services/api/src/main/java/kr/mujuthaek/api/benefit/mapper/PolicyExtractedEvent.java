package kr.mujuthaek.api.benefit.mapper;

import com.networknt.schema.Schema;
import com.networknt.schema.SchemaLocation;
import com.networknt.schema.SchemaRegistry;
import com.networknt.schema.SchemaRegistryConfig;
import com.networknt.schema.SpecificationVersion;
import java.io.IOException;
import java.io.InputStream;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import tools.jackson.databind.JsonNode;

/**
 * policy.extracted 이벤트 한 건에서 benefit이 저장하는 값 (contracts/events/policy.extracted.v1.json). 계약 검사는
 * 저장소의 JSON Schema를 한 번 컴파일해 수신 경계에서만 해요.
 */
public record PolicyExtractedEvent(
    UUID eventId,
    UUID rawPolicyId,
    int version,
    String sourceCode,
    String provider,
    String policyId,
    String field,
    boolean reprocess,
    String title,
    String agency,
    String regionScope,
    List<String> regionNames,
    List<String> regionCodes,
    List<String> categories,
    String detailUrl,
    String applyUrl,
    boolean relevant,
    String summary,
    List<Support> supports,
    LocalDate applyStart,
    LocalDate applyEnd,
    boolean applyAlways,
    LocalDate businessStart,
    LocalDate businessEnd,
    String scheduleText,
    String howToApply,
    List<String> documents,
    String contact,
    List<Condition> conditions,
    Double confidence,
    boolean needsReview,
    boolean reviewed,
    List<String> reviewReasons,
    boolean hasDocument,
    Instant extractedAt) {

  public static final String EVENT_TYPE = "policy.extracted";
  public static final int SCHEMA_VERSION = 1;

  /** 지원 내용 한 줄. amountMax는 만 원. */
  public record Support(
      String kind,
      Integer amountMax,
      String amountPer,
      Integer months,
      BigDecimal ratePct,
      String rawText,
      String evidence) {}

  /** 자격 조건 한 줄 (benefit-condition-types.draft.md). value는 JSON 글자, known=false면 null. */
  public record Condition(
      String type,
      String valueJson,
      int group,
      boolean known,
      String rawText,
      String evidence,
      double confidence,
      String origin) {}

  /** 계약에 맞지 않는 이벤트. 다시 받아도 같은 결과라 실패 큐로 보내요. */
  public static class InvalidEventException extends RuntimeException {
    public InvalidEventException(String message) {
      super(message);
    }
  }

  private static final String BASE = "https://mujuthaek.kr/contracts/";
  private static final Schema EVENT =
      SchemaRegistry.withDefaultDialect(
              SpecificationVersion.DRAFT_2020_12,
              builder ->
                  builder
                      .schemaRegistryConfig(
                          SchemaRegistryConfig.builder().formatAssertionsEnabled(true).build())
                      .schemas(
                          uri -> {
                            if (!uri.startsWith(BASE) || uri.contains("..")) {
                              throw new IllegalArgumentException("외부 계약 참조를 허용하지 않아요");
                            }
                            return resource(uri.substring(BASE.length()));
                          }))
          .getSchema(SchemaLocation.of(BASE + "events/policy.extracted.v1.json"));

  private static String resource(String name) {
    try (InputStream input = PolicyExtractedEvent.class.getResourceAsStream("/contracts/" + name)) {
      if (input == null) throw new IllegalStateException("패키지에 계약이 없어요: " + name);
      return new String(input.readAllBytes(), StandardCharsets.UTF_8);
    } catch (IOException e) {
      throw new IllegalStateException("계약 리소스를 읽을 수 없어요", e);
    }
  }

  /** 봉투에서 값을 꺼내요. 계약에 맞지 않으면 InvalidEventException (오류 메시지에 받은 값은 넣지 않아요). */
  public static PolicyExtractedEvent from(JsonNode envelope) {
    var errors = EVENT.validate(envelope);
    if (!errors.isEmpty()) {
      var first = errors.getFirst();
      throw new InvalidEventException(
          "SCHEMA " + first.getInstanceLocation() + ": " + first.getKeyword());
    }
    JsonNode p = envelope.path("payload");
    JsonNode source = p.path("source");
    JsonNode schedule = p.path("schedule");
    JsonNode quality = p.path("quality");
    List<Support> supports = new ArrayList<>();
    for (JsonNode s : p.path("supports")) {
      supports.add(
          new Support(
              s.path("kind").asString(),
              integer(s.path("amountMax")),
              text(s.path("amountPer")),
              integer(s.path("months")),
              decimal(s.path("ratePct")),
              s.path("rawText").asString(),
              s.path("evidence").asString()));
    }
    List<Condition> conditions = new ArrayList<>();
    for (JsonNode c : p.path("conditions")) {
      JsonNode value = c.path("value");
      conditions.add(
          new Condition(
              c.path("type").asString(),
              value.isObject() ? value.toString() : null,
              c.path("group").asInt(),
              c.path("known").asBoolean(),
              c.path("rawText").asString(),
              c.path("evidence").asString(),
              c.path("confidence").asDouble(),
              c.path("origin").asString()));
    }
    return new PolicyExtractedEvent(
        UUID.fromString(envelope.path("eventId").asString()),
        UUID.fromString(p.path("rawPolicyId").asString()),
        p.path("version").asInt(),
        p.path("sourceCode").asString(),
        p.path("provider").asString(),
        p.path("policyId").asString(),
        p.path("field").asString(),
        p.path("reprocess").asBoolean(),
        source.path("title").asString(),
        text(source.path("agency")),
        source.path("regionScope").asString(),
        strings(source.path("regionNames")),
        strings(source.path("regionCodes")),
        strings(source.path("categories")),
        text(source.path("detailUrl")),
        text(source.path("applyUrl")),
        p.path("relevant").asBoolean(),
        text(p.path("summary")),
        supports,
        date(schedule.path("applyStart")),
        date(schedule.path("applyEnd")),
        schedule.path("applyAlways").asBoolean(),
        date(schedule.path("businessStart")),
        date(schedule.path("businessEnd")),
        text(schedule.path("rawText")),
        text(p.path("howToApply")),
        strings(p.path("documents")),
        text(p.path("contact")),
        conditions,
        quality.path("confidence").isNumber() ? quality.path("confidence").asDouble() : null,
        quality.path("needsReview").asBoolean(),
        quality.path("reviewed").asBoolean(false), // 검수 결과 (선택 칸, 없으면 검수 전 결과)
        strings(quality.path("reviewReasons")),
        quality.path("hasDocument").asBoolean(),
        java.time.OffsetDateTime.parse(quality.path("extractedAt").asString()).toInstant());
  }

  private static String text(JsonNode node) {
    return node.isString() ? node.asString() : null;
  }

  private static Integer integer(JsonNode node) {
    return node.isInt() ? node.asInt() : null;
  }

  /** 지원 비율처럼 소수가 올 수 있는 숫자 (「연 3.5%」). */
  private static BigDecimal decimal(JsonNode node) {
    return node.isNumber() ? node.decimalValue() : null;
  }

  private static LocalDate date(JsonNode node) {
    return node.isString() ? LocalDate.parse(node.asString()) : null;
  }

  private static List<String> strings(JsonNode array) {
    List<String> out = new ArrayList<>();
    for (JsonNode item : array) out.add(item.asString());
    return out;
  }
}
