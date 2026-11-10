package kr.mujuthaek.api.notice.mapper;

import com.networknt.schema.Schema;
import com.networknt.schema.SchemaLocation;
import com.networknt.schema.SchemaRegistry;
import com.networknt.schema.SchemaRegistryConfig;
import com.networknt.schema.SpecificationVersion;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** 저장소의 JSON Schema를 한 번 컴파일해서 수신 경계에서 재사용해요. 조회·재계산에는 실행하지 않아요. */
public final class NoticeContract {
  private static final String BASE = "https://mujuthaek.kr/contracts/";
  private static final JsonMapper JSON = JsonMapper.builder().build();
  private static final Schema EVENT =
      registry().getSchema(SchemaLocation.of(BASE + "events/extraction.completed.v1.json"));
  static final JsonNode CONDITION_FIELDS =
      read("mappings/extraction-projection.v1.json").path("conditionFields");
  private static final Map<String, JsonNode> ATTRIBUTES = attributes();
  private static final Set<String> BLOCKING =
      Set.of("notice", "input", "documents", "sourceReferences", "evidence", "quality", "");

  /**
   * 공고 기본 정보 중 칸 단위로 보류할 수 있는 것 (계약 NOTICE_HOLDABLE, 2026-10-20). 제목·기관·분야와 /notice 전체는 보류할 수 없어요.
   */
  static final Set<String> NOTICE_HOLDABLE =
      Set.of("announcedOn", "supplyType", "description", "targetGroups", "counts");

  /** 보류할 수 있는 위치인지 (계약 holdable과 같은 규칙). */
  static boolean holdable(String target) {
    String[] parts = target.substring(1).split("/", -1);
    if (parts[0].equals("notice")) return parts.length >= 2 && NOTICE_HOLDABLE.contains(parts[1]);
    return !BLOCKING.contains(parts[0]);
  }

  private static final java.util.regex.Pattern SECRET =
      java.util.regex.Pattern.compile(
          "service[_-]*key\\s*=", java.util.regex.Pattern.CASE_INSENSITIVE);

  private NoticeContract() {}

  private static SchemaRegistry registry() {
    return SchemaRegistry.withDefaultDialect(
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
                    }));
  }

  private static String resource(String name) {
    try (InputStream input = NoticeContract.class.getResourceAsStream("/contracts/" + name)) {
      if (input == null) throw new IllegalStateException("패키지에 계약이 없어요: " + name);
      return new String(input.readAllBytes(), StandardCharsets.UTF_8);
    } catch (IOException e) {
      throw new IllegalStateException("계약 리소스를 읽을 수 없어요", e);
    }
  }

  private static JsonNode read(String name) {
    return JSON.readTree(resource(name));
  }

  private static Map<String, JsonNode> attributes() {
    Map<String, JsonNode> result = new HashMap<>();
    for (JsonNode item : read("schemas/eligibility-attributes.v1.json").path("attributes")) {
      result.put(item.path("code").asString(), item);
    }
    return Map.copyOf(result);
  }

  /** 입력 원문을 예외 메시지·로그에 복사하지 않아요. */
  public static void validate(JsonNode event) {
    var errors = EVENT.validate(event);
    if (!errors.isEmpty()) {
      var first = errors.getFirst();
      fail("SCHEMA", first.getInstanceLocation() + ": " + first.getKeyword());
    }
    checkTree(event, "");
    JsonNode payload = event.path("payload");
    JsonNode detail = payload.path("notice");
    JsonNode held = payload.path("heldItems");
    for (JsonNode item : held) {
      String target = item.path("target").asString();
      if (!target.startsWith("/")) fail("HELD_TARGET_NOT_ALLOWED", "/payload/heldItems");
      if (!holdable(target)) fail("HELD_TARGET_NOT_ALLOWED", "/payload/heldItems");
      if (detail.isObject() && detail.at(target).isMissingNode())
        fail("DANGLING_HELD_TARGET", "/payload/heldItems");
    }
    for (int i = 0; i < payload.path("conditions").size(); i++) {
      if (NoticeContent.held(held, "/eligibility/" + i)
          && !payload.path("conditions").get(i).path("inReview").asBoolean()) {
        fail("HELD_CONDITION_NOT_IN_REVIEW", "/payload/conditions/" + i);
      }
    }
    checkJudgment(payload);
    if (!detail.isObject()) return;
    for (String key : Set.of("rawPostId", "rawVersion", "field")) {
      if (!sameValue(payload.path(key), detail.path("input").path(key)))
        fail("EVENT_NOTICE_IDENTITY_CONFLICT", "/payload/" + key);
    }
    if (payload.path("reprocess").asBoolean(false)
        != detail.path("input").path("reprocess").asBoolean()) {
      fail("EVENT_REPROCESS_CONFLICT", "/payload/reprocess");
    }
    JsonNode eligibility = detail.path("eligibility");
    JsonNode conditions = payload.path("conditions");
    if (eligibility.size() != conditions.size())
      fail("EVENT_CONDITIONS_CONFLICT", "/payload/conditions");
    for (int i = 0;
        i < conditions.size();
        i++) // 조건 i = notice.eligibility[i] (ID 순서가 다르면 계약 검사기처럼 순서 충돌)
    if (!conditions.get(i).path("id").equals(eligibility.get(i).path("id")))
        fail("EVENT_CONDITIONS_CONFLICT", "/payload/conditions");
    for (int i = 0; i < conditions.size(); i++) {
      for (var field : CONDITION_FIELDS.properties()) {
        if (field.getKey().equals("scope") && !conditions.get(i).has("scope")) continue;
        if (!sameValue(
            conditions.get(i).path(field.getKey()),
            eligibility.get(i).at(field.getValue().asString()))) {
          fail(
              "EVENT_CONDITION_CONTENT_CONFLICT",
              "/payload/conditions/" + i + "/" + field.getKey());
        }
      }
    }
    JsonNode expectedTitle = detail.path("notice").path("title");
    if (expectedTitle.isNull())
      expectedTitle = detail.path("sourceReferences").get(0).path("sourceTitle");
    if (!payload.path("title").equals(expectedTitle))
      fail("EVENT_TITLE_CONFLICT", "/payload/title");
    String region = NoticeProjection.regionCode(detail);
    if (!java.util.Objects.equals(region, payload.path("regionCode").asString(null)))
      fail("EVENT_REGION_CONFLICT", "/payload/regionCode");
    if (!arrayOrEmpty(held).equals(arrayOrEmpty(detail.path("quality").path("heldItems")))) {
      fail("EVENT_HELD_ITEMS_CONFLICT", "/payload/heldItems");
    }
    boolean approved = "APPROVED".equals(payload.path("reviewStatus").asString());
    NoticeIntegrity.validate(
        detail,
        Set.of("AUTO_PASSED", "PARTIALLY_PASSED")
            .contains(payload.path("reviewStatus").asString()));
    // 바꾸기 전 규칙(표시 메모로도 접수 일정을 뺌)으로 만든 이벤트도 받아요: 그 규칙의 추출이 이미 보낸 이벤트·다시 보내는 이벤트가 바꾼 뒤 api에서
    // 막히지 않게(2026-11-10 재검토). 받은 값을 그대로 쓰므로 그 이벤트의 기간은 예전처럼 비어 있을 수 있어요
    if (payload.has("schedule")
        && !sameValue(payload.path("schedule"), NoticeProjection.schedule(detail, approved))
        && !sameValue(
            payload.path("schedule"), NoticeProjection.legacySchedule(detail, approved))) {
      fail("EVENT_SCHEDULE_CONFLICT", "/payload/schedule");
    }
    if (payload.has("applicationWindows")
        && !sameValue(
            payload.path("applicationWindows"), NoticeProjection.windows(detail, approved))
        && !sameValue(
            payload.path("applicationWindows"), NoticeProjection.legacyWindows(detail, approved))) {
      fail("EVENT_WINDOWS_CONFLICT", "/payload/applicationWindows");
    }
  }

  /** 분야별 판정 틀(판정 담당이 준 형식 그대로). 정책(POLICY)은 틀이 없어요. */
  private static final Map<String, String> JUDGMENT_SCHEMAS =
      Map.of(
          "HOUSING", "housing-judgment.v1",
          "BUSINESS_SPACE", "business-space-judgment.v1",
          "STARTUP_SUPPORT", "startup-support-judgment.v1",
          "SPACE_RECRUITMENT", "business-space-judgment.v1");

  /** 정책 수집에서 만든 판정 틀만 실어 오는 분야: 틀과 지원 지역(regionCodes)이 있어야 하고 상세(notice)는 없어요. */
  private static final Set<String> POLICY_FRAME_FIELDS =
      Set.of("STARTUP_SUPPORT", "SPACE_RECRUITMENT");

  /** 틀이 가리키는 원본 칸: 창업지원 틀은 수집 이벤트(raw.policy.collected)의 rawPolicyId예요. */
  private static final Map<String, String> JUDGMENT_SOURCE_KEY =
      Map.of("STARTUP_SUPPORT", "rawPolicyId");

  /** 정책 이벤트에만 있고 반드시 있는 칸: 지원 지역, 원문 주소(없으면 null), 상시 모집 여부 (계약 검사기 POLICY_ONLY_KEYS). */
  private static final java.util.List<String> POLICY_ONLY_KEYS =
      java.util.List.of("regionCodes", "detailUrl", "applyAlways");

  /** 판정 틀: 분야에 맞는 틀인지, 같은 공고·버전인지, 스키마로 못 잡는 ID 유일성(계약 검사기 judgment_errors와 같게). */
  private static void checkJudgment(JsonNode payload) {
    JsonNode judgment = payload.path("judgment");
    boolean policy = POLICY_FRAME_FIELDS.contains(payload.path("field").asString());
    if (policy
        && (!judgment.isObject()
            || POLICY_ONLY_KEYS.stream().anyMatch(key -> !payload.has(key))
            || payload.has("notice")
            || payload.has("heldItems")
            || !payload.path("conditions").isEmpty())) fail("EVENT_POLICY_FRAME_SHAPE", "/payload");
    if (!policy) {
      for (String key : POLICY_ONLY_KEYS)
        if (payload.has(key)) fail("EVENT_POLICY_FRAME_SHAPE", "/payload/" + key);
      // 마감일 대신 쓰는 신청 기간 안내도 정책에만 있어요 (없어도 되는 칸이라 POLICY_ONLY_KEYS와 따로 봐요)
      if (payload.has("applyNote")) fail("EVENT_POLICY_FRAME_SHAPE", "/payload/applyNote");
    }
    if (!judgment.isObject()) return;
    // 정책 틀의 검수 상태는 틀 전체로 정해요(heldItems 없음): 확인 필요 조건이 있는 틀은 자동 통과가 아니에요
    if (policy
        && "AUTO_PASSED".equals(payload.path("reviewStatus").asString(""))
        && anyInReview(judgment)) fail("EVENT_POLICY_REVIEW_STATUS", "/payload/reviewStatus");
    if (!judgment
        .path("schema")
        .asString("")
        .equals(JUDGMENT_SCHEMAS.get(payload.path("field").asString())))
      fail("EVENT_JUDGMENT_FIELD_CONFLICT", "/payload/judgment/schema");
    String sourceKey =
        JUDGMENT_SOURCE_KEY.getOrDefault(payload.path("field").asString(), "rawPostId");
    if (!sameValue(judgment.path(sourceKey), payload.path("rawPostId"))
        || !sameValue(judgment.path("rawVersion"), payload.path("rawVersion")))
      fail("EVENT_JUDGMENT_IDENTITY_CONFLICT", "/payload/judgment");
    java.util.List<String> ids = new java.util.ArrayList<>();
    for (var field : judgment.properties())
      if (!field.getKey().equals("notes")) collectIds(field.getValue(), ids);
    if (ids.size() != new java.util.HashSet<>(ids).size())
      fail("JUDGMENT_DUPLICATE_ID", "/payload/judgment");
  }

  /** 판정 틀 어디든(안내 notes 제외) inReview가 true인 조건이 있는지 (계약 검사기 _any_in_review). */
  private static boolean anyInReview(JsonNode node) {
    if (node.isObject()) {
      if (node.path("inReview").isBoolean() && node.path("inReview").asBoolean()) return true;
      for (var field : node.properties())
        if (!field.getKey().equals("notes") && anyInReview(field.getValue())) return true;
    } else if (node.isArray()) {
      for (JsonNode item : node) if (anyInReview(item)) return true;
    }
    return false;
  }

  private static void collectIds(JsonNode node, java.util.List<String> ids) {
    if (node.isObject()) {
      if (node.path("id").isString()) ids.add(node.path("id").asString());
      for (var field : node.properties())
        if (!field.getKey().equals("notes")) collectIds(field.getValue(), ids);
    } else if (node.isArray()) {
      for (JsonNode item : node) collectIds(item, ids);
    }
  }

  private static JsonNode arrayOrEmpty(JsonNode node) {
    return node.isMissingNode() ? JSON.createArrayNode() : node;
  }

  /** JSON Schema의 수치 동일성: 1과 1.0은 같은 수예요. 문자열·불리언·배열 순서는 구분해요. */
  static boolean sameValue(JsonNode left, JsonNode right) {
    if (left.isNumber() && right.isNumber())
      return left.decimalValue().compareTo(right.decimalValue()) == 0;
    if (left.isObject() && right.isObject()) {
      if (left.size() != right.size()) return false;
      for (var field : left.properties())
        if (!right.has(field.getKey()) || !sameValue(field.getValue(), right.path(field.getKey())))
          return false;
      return true;
    }
    if (left.isArray() && right.isArray()) {
      if (left.size() != right.size()) return false;
      for (int i = 0; i < left.size(); i++) if (!sameValue(left.get(i), right.get(i))) return false;
      return true;
    }
    return left.equals(right);
  }

  /** 사전 기반 속성 검사와 공개 URL 보호. 구조 검사를 통과한 트리만 한 번 순회해요. */
  private static void checkTree(JsonNode node, String path) {
    if (node.isObject()) {
      if ("ATOMIC".equals(node.path("kind").asString(""))) checkAtomic(node, path);
      for (var field : node.properties()) {
        String name = field.getKey();
        JsonNode value = field.getValue();
        String child = path + "/" + name.replace("~", "~0").replace("/", "~1");
        if ((name.equals("regionCode") || name.equals("regionCodes"))
            && value.isString()
            && !NoticeProjection.regionCodeValid(value.asString()))
          fail("REGION_CODE_HIERARCHY", child);
        if (name.equals("regionCodes")
            && value.isArray()) { // 판정 틀의 regionCodes 등 배열 원소도(계약 검사기와 같게)
          for (int i = 0; i < value.size(); i++)
            if (value.get(i).isString()
                && !NoticeProjection.regionCodeValid(value.get(i).asString()))
              fail("REGION_CODE_HIERARCHY", child + "/" + i);
        }
        if ((name.equals("url") || name.endsWith("Url"))
            && value.isString()
            && NoticeProjection.privateUrl(value.asString())) fail("PRIVATE_URL", child);
        if ((name.equals("url") || name.endsWith("Url")) && value.isArray()) {
          for (int i = 0; i < value.size(); i++)
            if (value.get(i).isString() && NoticeProjection.privateUrl(value.get(i).asString()))
              fail("PRIVATE_URL", child + "/" + i);
        }
        checkTree(value, child);
      }
    } else if (node.isArray()) {
      for (int i = 0; i < node.size(); i++) checkTree(node.get(i), path + "/" + i);
    } else if (node.isString() && SECRET.matcher(node.asString()).find()) {
      fail("PRIVATE_URL", path);
    }
  }

  private static void checkAtomic(JsonNode node, String path) {
    JsonNode spec = ATTRIBUTES.get(node.path("attribute").asString());
    if (spec == null) {
      fail("ATTRIBUTE_UNKNOWN", path);
      return;
    }
    if (!spec.path("unit").equals(node.path("unit"))) fail("ATTRIBUTE_UNIT_CONFLICT", path);
    if (!contains(spec.path("operators"), node.path("operator")))
      fail("ATTRIBUTE_OPERATOR_CONFLICT", path);
    if (spec.path("benchmarkRequired").asBoolean(false) && node.path("benchmark").isNull())
      fail("BENCHMARK_REQUIRED", path);
    JsonNode value = node.path("value");
    if (value.isArray()) {
      for (JsonNode item : value) checkValue(spec, item, path);
    } else checkValue(spec, value, path);
  }

  private static void checkValue(JsonNode spec, JsonNode value, String path) {
    boolean valid =
        switch (spec.path("valueType").asString()) {
          case "boolean" -> value.isBoolean();
          case "integer" -> value.isIntegralNumber();
          case "number" -> value.isNumber();
          case "string" -> value.isString() && !value.asString().isEmpty();
          default -> false;
        };
    if (valid && spec.has("minimum") && value.isNumber())
      valid = value.decimalValue().compareTo(spec.path("minimum").decimalValue()) >= 0;
    if (valid && spec.has("pattern"))
      valid = value.asString().matches(spec.path("pattern").asString());
    if (valid && spec.has("enum")) valid = contains(spec.path("enum"), value);
    if (valid && spec.path("regionCode").asBoolean(false))
      valid = NoticeProjection.regionCodeValid(value.asString());
    if (!valid) fail("ATTRIBUTE_VALUE_INVALID", path); // 계약 검사기와 같은 코드
  }

  private static boolean contains(JsonNode array, JsonNode value) {
    for (JsonNode item : array) if (item.equals(value)) return true;
    return false;
  }

  static void fail(String code, String path) {
    throw new ExtractionEvent.InvalidEventException(code + " " + path);
  }
}
