package kr.mujuthaek.api.notice.mapper;

import static kr.mujuthaek.api.notice.mapper.NoticeContract.fail;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import tools.jackson.databind.JsonNode;

/** 수신 내용의 참조·수치·완료 조건. 원문 인용의 진위는 extraction 검증기가 담당해요. */
final class NoticeIntegrity {
  private record Entry(String path, JsonNode node) {}

  private final JsonNode data;
  private final JsonNode quality;
  private final boolean ready;
  private final boolean partial;
  private final List<Entry> nodes = new ArrayList<>();
  private final Map<String, JsonNode> locations;
  private final Map<String, JsonNode> groups;
  private final Map<String, JsonNode> documents;
  private final Map<String, JsonNode> evidence;

  static void validate(JsonNode data, boolean ready) {
    new NoticeIntegrity(data, ready).check();
  }

  private NoticeIntegrity(JsonNode data, boolean ready) {
    this.data = data;
    this.quality = data.path("quality");
    this.ready = ready;
    this.partial =
        "PARTIALLY_PASSED".equals(quality.path("verification").path("status").asString());
    collect(data, "");
    locations = index(data.path("locations"));
    groups = index(data.path("supplyGroups"));
    documents = index(data.path("documents"));
    evidence = index(data.path("evidence"));
  }

  private static Map<String, JsonNode> index(JsonNode array) {
    Map<String, JsonNode> result = new HashMap<>();
    for (JsonNode node : array) result.put(node.path("id").asString(), node);
    return result;
  }

  private void collect(JsonNode node, String path) {
    if (node.isObject()) {
      nodes.add(new Entry(path, node));
      for (var field : node.properties())
        collect(
            field.getValue(), path + "/" + field.getKey().replace("~", "~0").replace("/", "~1"));
    } else if (node.isArray())
      for (int i = 0; i < node.size(); i++) collect(node.get(i), path + "/" + i);
  }

  private void required(String code, String path) {
    if (!ready) return;
    String target = path;
    if (path.startsWith("/quality/coverage/"))
      target = "/" + path.substring("/quality/coverage/".length());
    if (path.startsWith("/quality/missingFields/"))
      target = data.at(path).path("target").asString();
    if (!(partial && underHeld(target))) fail(code, path);
  }

  private void check() {
    Set<String> ids = new HashSet<>();
    for (Entry entry : nodes) {
      String p = entry.path();
      JsonNode n = entry.node();
      if (n.has("id") && !ids.add(n.path("id").asString())) fail("DUPLICATE_ID", p);
      for (JsonNode id : n.path("evidenceIds"))
        if (!evidence.containsKey(id.asString())) fail("DANGLING_EVIDENCE", p);
      if (n.hasNonNull("locationId") && !locations.containsKey(n.path("locationId").asString()))
        fail("DANGLING_LOCATION", p);
      if (n.hasNonNull("parentLocationId")) {
        JsonNode parent = locations.get(n.path("parentLocationId").asString());
        if (parent == null
            || !"BUILDING".equals(n.path("kind").asString())
            || !"COMPLEX".equals(parent.path("kind").asString()))
          fail("INVALID_LOCATION_PARENT", p);
      }
      if (n.has("scope")) {
        JsonNode scope = n.path("scope");
        for (JsonNode id : scope.path("locationIds"))
          if (!locations.containsKey(id.asString())) fail("DANGLING_SCOPE", p);
        for (JsonNode id : scope.path("supplyGroupIds")) {
          JsonNode group = groups.get(id.asString());
          if (group == null) {
            fail("DANGLING_SCOPE", p);
            return;
          }
          if (!scope.path("locationIds").isEmpty()
              && !contains(scope.path("locationIds"), group.path("locationId")))
            fail("SCOPE_LOCATION_CONFLICT", p);
        }
        if (!"RESOLVED".equals(scope.path("resolution").asString()))
          required("UNRESOLVED_SCOPE", p);
      }
      if ("ATOMIC".equals(n.path("kind").asString(""))) {
        if ("BETWEEN".equals(n.path("operator").asString())
            && n.path("value")
                    .get(0)
                    .decimalValue()
                    .compareTo(n.path("value").get(1).decimalValue())
                > 0) fail("REVERSED_RANGE", p);
        JsonNode b = n.path("benchmark");
        if ("INCOME_BENCHMARK_PERCENT".equals(n.path("attribute").asString())
            && !b.isNull()
            && (b.path("householdScope").isNull()
                || (b.path("referenceYear").isNull() && b.path("referenceVersion").isNull())))
          fail("INCOMPLETE_INCOME_BENCHMARK", p);
      }
      if (n.has("startsAt")) {
        boolean application = contains(n.path("kinds"), "APPLICATION");
        if (application == "NOT_APPLICABLE".equals(n.path("applicationMode").asString()))
          fail("APPLICATION_MODE_CONFLICT", p);
        if (!n.path("startsAt").isNull()
            && !n.path("endsAt").isNull()
            && bound(n.path("startsAt"), false).isAfter(bound(n.path("endsAt"), true)))
          fail("REVERSED_SCHEDULE", p);
        // 하루 안의 시각 구간(HH:MM)은 글자 비교가 곧 시각 비교예요 (계약 TIME_RANGE_REVERSED, 2026-10-23)
        for (String key : List.of("dailyHours", "breaks")) {
          JsonNode spans = n.path(key);
          for (int i = 0; i < spans.size(); i++)
            if (spans
                    .get(i)
                    .path("start")
                    .asString("")
                    .compareTo(spans.get(i).path("end").asString(""))
                >= 0) fail("TIME_RANGE_REVERSED", p + "/" + key + "/" + i);
        }
        JsonNode places = n.path("places");
        for (int i = 0; i < places.size(); i++) {
          JsonNode place = places.get(i);
          if (place.path("name").isNull()
              && place.path("address").isNull()
              && place.path("detail").isNull()) fail("EMPTY_PLACE", p + "/places/" + i);
        }
      }
      for (var pair :
          Map.of("exclusiveAreaSqm", "exclusiveAreaRange", "amountKrw", "amountRangeKrw")
              .entrySet()) {
        if (n.has(pair.getKey()) && n.hasNonNull(pair.getValue())) {
          JsonNode span = n.path(pair.getValue());
          if (span.path("min").decimalValue().compareTo(span.path("max").decimalValue()) > 0)
            fail("RANGE_REVERSED", p + "/" + pair.getValue());
          if (!n.path(pair.getKey()).isNull())
            fail("RANGE_WITH_SINGLE_VALUE", p + "/" + pair.getValue());
        }
      }
      if (n.has("amountKrw")) {
        String expected =
            Map.of("MONTHLY_RENT", "MONTHLY", "ANNUAL_RENT", "ANNUAL")
                .get(n.path("kind").asString());
        if (expected != null
            && !Set.of(expected, "UNKNOWN").contains(n.path("billingPeriod").asString()))
          fail("PRICE_PERIOD_CONFLICT", p);
        if (Set.of("EXEMPT", "NOT_APPLICABLE", "UNKNOWN")
                .contains(n.path("taxTreatment").asString())
            && !n.path("vatRate").isNull()) fail("VAT_CONFLICT", p);
      }
      if (n.hasNonNull("initialMonths")
          && n.hasNonNull("maxMonths")
          && n.path("initialMonths").decimalValue().compareTo(n.path("maxMonths").decimalValue())
              > 0) fail("LEASE_TERM_CONFLICT", p);
      if ("SCORING".equals(n.path("kind").asString(""))
          && n.hasNonNull("points")
          && n.hasNonNull("maxPoints")
          && n.path("points").decimalValue().compareTo(n.path("maxPoints").decimalValue()) > 0)
        fail("SCORE_EXCEEDS_MAX", p);
      if ("NOT_REVIEWED".equals(n.path("exceptionsStatus").asString("")))
        required("EXCEPTIONS_NOT_REVIEWED", p);
    }
    evidence();
    counts();
    sources();
    quality();
  }

  private static Instant bound(JsonNode time, boolean end) {
    String raw = time.path("value").asString();
    return switch (time.path("precision").asString()) {
      case "MINUTE" -> java.time.OffsetDateTime.parse(raw).toInstant();
      case "MONTH" ->
          (end ? YearMonth.parse(raw).atEndOfMonth().plusDays(1) : YearMonth.parse(raw).atDay(1))
              .atStartOfDay()
              .toInstant(ZoneOffset.ofHours(9))
              .minusNanos(end ? 1 : 0);
      default ->
          (end ? LocalDate.parse(raw).plusDays(1) : LocalDate.parse(raw))
              .atStartOfDay()
              .toInstant(ZoneOffset.ofHours(9))
              .minusNanos(end ? 1 : 0);
    };
  }

  private void evidence() {
    for (JsonNode e : data.path("evidence")) {
      JsonNode doc = documents.get(e.path("sourceId").asString());
      if (doc == null) {
        fail("DANGLING_SOURCE", "/evidence");
        return;
      }
      JsonNode loc = e.path("locator");
      String kind = loc.path("kind").asString();
      if (!Map.of("PDF_PAGE", "PDF", "TEXT_RANGE", "TEXT", "UNIT_ROW", "UNITS")
          .get(kind)
          .equals(doc.path("kind").asString())) fail("LOCATOR_SOURCE_CONFLICT", "/evidence");
      if (kind.equals("PDF_PAGE")) {
        if (doc.hasNonNull("pageCount") && loc.path("page").asInt() > doc.path("pageCount").asInt())
          fail("PAGE_OUT_OF_RANGE", "/evidence");
        if (ready && doc.path("pageCount").isNull()) fail("PAGE_COUNT_REQUIRED", "/evidence");
      }
      if (kind.equals("TEXT_RANGE")) {
        if (loc.path("start").asInt() >= loc.path("end").asInt())
          fail("EMPTY_TEXT_RANGE", "/evidence");
        // 쪽 표시가 있는 PDF 글자의 쪽 번호(선택): 문서 쪽 수를 알면 그 안이어야 해요
        if (loc.hasNonNull("page")
            && doc.hasNonNull("pageCount")
            && loc.path("page").asInt() > doc.path("pageCount").asInt())
          fail("PAGE_OUT_OF_RANGE", "/evidence");
      }
    }
  }

  private void counts() {
    Map<String, JsonNode> counts = new HashMap<>(), pools = new HashMap<>();
    Map<String, List<JsonNode>> children = new HashMap<>();
    for (Entry e : nodes)
      if (e.node().has("aggregationRole")) {
        JsonNode n = e.node();
        counts.put(n.path("id").asString(), n);
        if (n.hasNonNull("parentCountId"))
          children
              .computeIfAbsent(n.path("parentCountId").asString(), ignored -> new ArrayList<>())
              .add(n);
        if (n.hasNonNull("allocationPoolId")) {
          JsonNode first = pools.putIfAbsent(n.path("allocationPoolId").asString(), n);
          if (first != null
              && (!first.path("kind").equals(n.path("kind"))
                  || !first.path("value").equals(n.path("value"))))
            fail("ALLOCATION_POOL_CONFLICT", "/supplyGroups");
        }
      }
    for (var e : counts.entrySet()) {
      JsonNode n = e.getValue();
      if (n.hasNonNull("parentCountId")) {
        JsonNode parent = counts.get(n.path("parentCountId").asString());
        if (parent == null
            || parent == n
            || !"TOTAL".equals(parent.path("aggregationRole").asString()))
          fail("INVALID_COUNT_PARENT", "/supplyGroups");
        if (!parent.path("kind").equals(n.path("kind")))
          fail("COUNT_CONCEPT_CONFLICT", "/supplyGroups");
      }
      List<JsonNode> parts = children.getOrDefault(e.getKey(), List.of());
      boolean complete = n.path("aggregationComplete").asBoolean();
      if (complete
          && (!"TOTAL".equals(n.path("aggregationRole").asString())
              || parts.isEmpty()
              || n.path("value").isNull()
              || parts.stream().anyMatch(c -> c.path("value").isNull())))
        fail("INCOMPLETE_COUNT_COMPONENTS", "/supplyGroups");
      Set<String> seenPools = new HashSet<>();
      BigDecimal sum = BigDecimal.ZERO;
      for (JsonNode child : parts)
        if (!child.path("value").isNull()
            && (!child.hasNonNull("allocationPoolId")
                || seenPools.add(child.path("allocationPoolId").asString())))
          sum = sum.add(child.path("value").decimalValue());
      if (complete && sum.compareTo(n.path("value").decimalValue()) != 0)
        fail("COUNT_SUM_MISMATCH", "/supplyGroups");
      if (!complete
          && !n.path("value").isNull()
          && sum.compareTo(n.path("value").decimalValue()) > 0)
        fail("COUNT_COMPONENTS_EXCEED_TOTAL", "/supplyGroups");
    }
  }

  private void sources() {
    Set<String> seen = new HashSet<>();
    boolean matches = false;
    for (JsonNode r : data.path("sourceReferences")) {
      String key =
          r.path("sourceCode").asString()
              + "\n"
              + r.path("rawPostId").asString()
              + "\n"
              + r.path("rawVersion").asInt();
      if (!seen.add(key)) fail("DUPLICATE_SOURCE_REFERENCE", "/sourceReferences");
      if (r.path("supersedesPostId").equals(r.path("rawPostId")))
        fail("SELF_SUPERSEDES", "/sourceReferences");
      if ("NOTICE".equals(r.path("kind").asString()) && !r.path("supersedesPostId").isNull())
        fail("NOTICE_HAS_SUPERSEDES", "/sourceReferences");
      if (ready
          && !"NOTICE".equals(r.path("kind").asString())
          && r.path("supersedesPostId").isNull())
        fail("UNLINKED_RELATED_NOTICE", "/sourceReferences");
      matches |=
          r.path("rawPostId").equals(data.path("input").path("rawPostId"))
              && NoticeContract.sameValue(
                  r.path("rawVersion"), data.path("input").path("rawVersion"));
    }
    if (!matches) fail("INPUT_REFERENCE_MISMATCH", "/input");
    if (!data.path("notice").path("field").isNull()
        && !data.path("notice").path("field").equals(data.path("input").path("field")))
      fail("INPUT_FIELD_MISMATCH", "/input/field");
    // 공고 전체 신청 방법은 신청 일정에서 계산한 값과 같아야 해요 (계약 APPLICATION_CHANNELS_CONFLICT, 2026-10-23)
    List<String> given = new ArrayList<>();
    data.path("notice").path("applicationChannels").forEach(c -> given.add(c.asString()));
    if (!given.equals(NoticeProjection.applicationChannels(data)))
      fail("APPLICATION_CHANNELS_CONFLICT", "/notice/applicationChannels");
  }

  private void quality() {
    for (var entry : quality.path("coverage").properties()) {
      String section = entry.getKey(), status = entry.getValue().path("status").asString();
      if (!section.equals("notice")) {
        if (status.equals("EXTRACTED") && data.path(section).isEmpty())
          fail("EMPTY_EXTRACTED_SECTION", "/quality/coverage/" + section);
        if (Set.of("NOT_APPLICABLE", "NOT_IN_SOURCE", "NOT_ATTEMPTED", "FAILED").contains(status)
            && !data.path(section).isEmpty())
          fail("COVERAGE_CONTENT_CONFLICT", "/quality/coverage/" + section);
      }
      if (Set.of("NOT_ATTEMPTED", "FAILED").contains(status)
          || (Set.of("notice", "eligibility").contains(section) && status.equals("PARTIAL")))
        required("INCOMPLETE_EXTRACTION", "/quality/coverage/" + section);
    }
    for (String name : List.of("missingFields", "reviewIssues", "notes", "heldItems")) {
      Set<String> seen = new HashSet<>();
      int i = 0;
      for (JsonNode entry : quality.path(name)) {
        String target = entry.path("target").asString(), path = "/quality/" + name + "/" + i++;
        JsonNode actual = data.at(target);
        if (actual.isMissingNode())
          fail(name.equals("heldItems") ? "DANGLING_HELD_TARGET" : "DANGLING_FIELD_POINTER", path);
        if (name.equals("missingFields")) {
          if (!seen.add(target)) fail("DUPLICATE_FIELD_RECORD", path);
          if (!actual.isNull() && !(actual.isArray() && actual.isEmpty()))
            fail("MISSING_FIELD_HAS_VALUE", path);
          if (!Set.of("NOT_IN_SOURCE", "NOT_APPLICABLE", "TO_BE_ANNOUNCED")
                  .contains(entry.path("reason").asString())
              && criticalSection(target)) required("UNRESOLVED_MISSING_FIELD", path);
        }
      }
    }
    comparison();
    if (!ready) return;
    if (!Set.of("PASSED", "PARTIALLY_PASSED")
        .contains(quality.path("verification").path("status").asString()))
      fail("VERIFICATION_REQUIRED", "/quality/verification");
    if (partial && quality.path("heldItems").isEmpty())
      fail("HELD_ITEMS_REQUIRED", "/quality/heldItems");
    for (JsonNode issue : quality.path("reviewIssues")) {
      if (!partial) fail("UNRESOLVED_REVIEW_ISSUES", "/quality/reviewIssues");
      String target = issue.path("target").asString();
      if (target.startsWith("/quality/coverage/"))
        target = "/" + target.substring("/quality/coverage/".length());
      if (target.startsWith("/quality/missingFields/"))
        target = data.at(target).path("target").asString();
      if (!underHeld(target)) fail("REVIEW_ISSUE_NOT_HELD", "/quality/reviewIssues");
    }
    if (partial) {
      // API 불일치로 부분 게시하려면 불일치한 칸이 모두 보류돼 있어야 해요(보류 밖이면 틀린 값이 게시됨)
      JsonNode fields = quality.path("verification").path("apiComparison").path("fields");
      for (int i = 0; i < fields.size(); i++) {
        JsonNode field = fields.get(i);
        if ("MISMATCH".equals(field.path("status").asString())
            && !underHeld(field.path("target").asString()))
          fail("API_MISMATCH_NOT_HELD", "/quality/verification/apiComparison/fields/" + i);
      }
    }
    for (String key : List.of("title", "publisher", "field", "supplyType"))
      if (data.path("notice").path(key).isNull()) fail("MISSING_NOTICE_CORE", "/notice");
    Set<String> explained = new HashSet<>();
    for (JsonNode m : quality.path("missingFields")) explained.add(m.path("target").asString());
    List<String> unknowns = new ArrayList<>(List.of("/notice/announcedOn"));
    for (int i = 0; i < data.path("locations").size(); i++)
      unknowns.add("/locations/" + i + "/regionCode");
    for (int i = 0; i < data.path("supplyGroups").size(); i++) {
      JsonNode prices = data.path("supplyGroups").get(i).path("prices");
      for (int j = 0; j < prices.size(); j++)
        if (!prices.get(j).hasNonNull("amountRangeKrw"))
          unknowns.add("/supplyGroups/" + i + "/prices/" + j + "/amountKrw");
    }
    for (String target : unknowns)
      if (data.at(target).isNull() && !explained.contains(target))
        required("UNKNOWN_REASON_REQUIRED", target);
  }

  private void comparison() {
    JsonNode c = quality.path("verification").path("apiComparison"),
        identity = c.path("referenceIdentity");
    if (!identity.isNull()) {
      boolean found = false;
      for (JsonNode reference : data.path("sourceReferences")) {
        boolean same = true;
        for (var field : identity.properties())
          same &= field.getValue().equals(reference.path(field.getKey()));
        found |= same;
      }
      if (!found)
        fail(
            "API_REFERENCE_IDENTITY_CONFLICT",
            "/quality/verification/apiComparison/referenceIdentity");
    }
    Set<String> statuses = new HashSet<>();
    for (JsonNode f : c.path("fields")) {
      String status = f.path("status").asString();
      statuses.add(status);
      if (status.equals("MATCH")
          && (f.path("expected").isNull() || !sameJson(f.path("expected"), f.path("actual"))))
        fail("FALSE_API_MATCH", "/quality/verification/apiComparison/fields");
      if (status.equals("MISMATCH") && sameJson(f.path("expected"), f.path("actual")))
        fail("FALSE_API_MISMATCH", "/quality/verification/apiComparison/fields");
      if (status.equals("NOT_COMPARABLE") && f.path("reason").isNull())
        fail("COMPARISON_REASON_REQUIRED", "/quality/verification/apiComparison/fields");
      JsonNode target = data.at(f.path("target").asString());
      if (target.isMissingNode()) // 가리키는 칸이 없음(계약 검사기와 같은 코드)
      fail("DANGLING_API_TARGET", "/quality/verification/apiComparison/fields");
      if (!sameJson(target, f.path("actual")))
        fail("API_ACTUAL_VALUE_CONFLICT", "/quality/verification/apiComparison/fields");
    }
    String status = c.path("status").asString();
    if (status.equals("MATCHED") && (!statuses.contains("MATCH") || statuses.contains("MISMATCH")))
      fail("INVALID_API_MATCH", "/quality/verification/apiComparison");
    if (status.equals("MISMATCH") && !statuses.contains("MISMATCH"))
      fail("INVALID_API_MISMATCH", "/quality/verification/apiComparison");
    if (status.equals("NO_COMPARABLE_FIELDS")
        && statuses.stream().anyMatch(s -> !s.equals("NOT_COMPARABLE")))
      fail("API_COMPARABLE_FIELD_FOUND", "/quality/verification/apiComparison");
  }

  private static boolean contains(JsonNode array, JsonNode value) {
    for (JsonNode node : array) if (node.equals(value)) return true;
    return false;
  }

  private static boolean contains(JsonNode array, String value) {
    for (JsonNode node : array) if (value.equals(node.asString())) return true;
    return false;
  }

  private boolean underHeld(String pointer) {
    for (JsonNode item : quality.path("heldItems")) {
      String target = item.path("target").asString();
      if (pointer.equals(target) || pointer.startsWith(target + "/")) return true;
    }
    return false;
  }

  /** 판정에 쓰는 섹션(공고 기본 정보·자격)을 가리키는지. 계약 검사기 _section과 같게 섹션 자체(/notice)도 포함해요. */
  private static boolean criticalSection(String target) {
    String section = target.replaceFirst("^/", "").split("/", 2)[0];
    return section.equals("notice") || section.equals("eligibility");
  }

  /**
   * JSON 값이 같은지 계약 검사기(Python ==)와 같은 기준으로 봐요. 숫자는 값으로 비교하고(1 = 1.0), 참·거짓은 1·0과 같아요. 객체·배열은 안쪽까지
   * 같은 기준으로 비교해요. JsonNode.equals는 1과 1.0을 다르게 봐서, 계약을 통과한 이벤트가 실패 큐로 갈 수 있었어요(2026-10-21).
   */
  static boolean sameJson(JsonNode a, JsonNode b) {
    if (numeric(a) && numeric(b)) return number(a).compareTo(number(b)) == 0;
    if (a.isArray() && b.isArray()) {
      if (a.size() != b.size()) return false;
      for (int i = 0; i < a.size(); i++) if (!sameJson(a.get(i), b.get(i))) return false;
      return true;
    }
    if (a.isObject() && b.isObject()) {
      if (a.size() != b.size()) return false;
      for (java.util.Map.Entry<String, JsonNode> entry : a.properties()) {
        if (!b.has(entry.getKey()) || !sameJson(entry.getValue(), b.get(entry.getKey())))
          return false;
      }
      return true;
    }
    return a.equals(b);
  }

  private static boolean numeric(JsonNode node) {
    return node.isNumber() || node.isBoolean();
  }

  private static BigDecimal number(JsonNode node) {
    return node.isBoolean()
        ? (node.asBoolean() ? BigDecimal.ONE : BigDecimal.ZERO)
        : node.decimalValue();
  }
}
