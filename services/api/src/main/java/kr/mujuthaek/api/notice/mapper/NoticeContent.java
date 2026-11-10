package kr.mujuthaek.api.notice.mapper;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.UUID;
import kr.mujuthaek.api.common.event.NoticeLocationsChanged;
import kr.mujuthaek.api.notice.domain.ApplicationStatusCalculator.Window;
import kr.mujuthaek.api.notice.domain.ReviewStatus;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.MissingNode;
import tools.jackson.databind.node.ObjectNode;

/** 추출 결과의 내용에서 notice가 쓰는 값을 꺼내요: 내용 해시, 바뀐 섹션, 원본 글 종류. */
public final class NoticeContent {

  /** 상세 공고에서 비교하는 섹션 (바뀌면 NoticeUpdated.changedFields에 이름이 들어가요). */
  static final List<String> SECTIONS =
      List.of(
          "notice",
          "locations",
          "supplyGroups",
          "schedules",
          "eligibility",
          "selectionRules",
          "requiredDocuments",
          "guidance");

  private NoticeContent() {}

  /**
   * 내용 해시. 받을 때마다 달라지는 칸(입력 이벤트 ID, 검증 시각)을 빼고, 객체 칸 순서와 상관없이 같은 내용이면 같은 값이에요. 배열 순서는 의미가 있어(순위·가점
   * 행) 그대로 둬요.
   */
  public static String hash(ExtractionEvent event) {
    StringBuilder canonical = new StringBuilder();
    for (Map.Entry<String, JsonNode> part : comparableParts(event).entrySet()) {
      canonical.append(part.getKey()).append('=');
      write(part.getValue(), canonical);
      canonical.append('\n');
    }
    try {
      byte[] digest =
          MessageDigest.getInstance("SHA-256")
              .digest(canonical.toString().getBytes(StandardCharsets.UTF_8));
      return HexFormat.of().formatHex(digest);
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException(e);
    }
  }

  /**
   * 이전 공개 버전과 비교해 달라진 섹션 이름. 판정용 조건(conditions)·보류 항목(heldItems)·접수 기간(applicationWindows)·판정
   * 틀(judgment)도 비교해요. 내용 해시에 들어가는 부분은 모두 비교해, 새 버전인데 바뀐 섹션이 비는 일이 없게 해요.
   *
   * @param previousJudgment 이전 버전의 판정 틀 (없으면 null)
   */
  public static List<String> changedSections(
      JsonNode previousSnapshot,
      JsonNode previousConditions,
      JsonNode previousHeldItems,
      JsonNode previousApplicationWindows,
      JsonNode previousJudgment,
      ExtractionEvent current) {
    List<String> changed = new ArrayList<>();
    for (String section : SECTIONS) {
      if (!same(previousSnapshot.path(section), current.notice().path(section))) {
        changed.add(section);
      }
    }
    if (!same(previousConditions, current.conditions())) {
      changed.add("conditions");
    }
    if (!same(previousHeldItems, current.heldItems())) {
      changed.add("heldItems");
    }
    if (!same(previousApplicationWindows, current.applicationWindows())) {
      changed.add("applicationWindows");
    }
    if (!same(previousJudgment, current.judgment())) {
      changed.add("judgment");
    }
    return changed;
  }

  /** 정정이 통째로 바꾸면 안 되는 핵심 섹션(공급·자격·위치). */
  private static final List<String> CORE_SECTIONS =
      List.of("supplyGroups", "eligibility", "locations");

  /**
   * 지금 공개된 버전에는 쓸 항목이 있는데 정정 결과에는 없는(비었거나 모두 보류) 핵심 섹션. 「당첨자 발표일 변경」 같은 짧은 정정 안내는 바뀐 일정만 있어, 통째로 새
   * 버전으로 바꾸면 공급·자격·위치가 사라지고 원공고로 되돌릴 수도 없었어요(2026-11-10 재검토).
   */
  public static List<String> droppedCoreSections(
      JsonNode previousSnapshot, JsonNode previousHeldItems, ExtractionEvent current) {
    return droppedCoreSections(
        previousSnapshot, previousHeldItems, current.notice(), current.heldItems());
  }

  static List<String> droppedCoreSections(
      JsonNode previousSnapshot, JsonNode previousHeldItems, JsonNode detail, JsonNode heldItems) {
    List<String> dropped = new ArrayList<>();
    for (String section : CORE_SECTIONS) {
      if (usable(previousSnapshot.path(section), previousHeldItems, section) > 0
          && (detail == null || usable(detail.path(section), heldItems, section) == 0)) {
        dropped.add(section);
      }
    }
    return dropped;
  }

  /** 섹션 항목 중 통째로 보류하지 않은 것의 수(칸 하나만 보류한 항목은 셈). */
  private static int usable(JsonNode items, JsonNode heldItems, String section) {
    if (!items.isArray()) {
      return 0;
    }
    int count = 0;
    for (int i = 0; i < items.size(); i++) {
      String pointer = "/" + section + "/" + i;
      boolean whole = false;
      for (JsonNode held : heldItems == null ? List.<JsonNode>of() : heldItems) {
        String target = held.path("target").asString("");
        if (!target.isEmpty() && (pointer.equals(target) || pointer.startsWith(target + "/"))) {
          whole = true;
          break;
        }
      }
      if (!whole) {
        count++;
      }
    }
    return count;
  }

  /** 비교에 쓰는 부분. 받을 때마다 달라지는 칸은 빼요. */
  private static Map<String, JsonNode> comparableParts(ExtractionEvent event) {
    Map<String, JsonNode> parts = new TreeMap<>();
    if (event.notice() != null) {
      ObjectNode notice = (ObjectNode) event.notice().deepCopy();
      notice.remove("input"); // eventId 등 받을 때마다 달라짐
      if (notice.path("quality").path("verification") instanceof ObjectNode verification) {
        verification.remove("checkedAt");
      }
      parts.put("notice", notice);
    }
    parts.put("conditions", event.conditions());
    parts.put("heldItems", event.heldItems());
    parts.put("applicationWindows", event.applicationWindows());
    if (event.judgment() != null) { // 판정 틀이 없는 이전 이벤트의 해시는 그대로 두려고 있을 때만 넣어요
      parts.put("judgment", event.judgment());
    }
    return parts;
  }

  private static String canonical(JsonNode node) {
    StringBuilder out = new StringBuilder();
    write(node, out);
    return out.toString();
  }

  /** 객체 칸을 이름순으로 쓴 JSON. 같은 내용이면 같은 글자가 나와요. */
  private static void write(JsonNode node, StringBuilder out) {
    if (node == null || node.isMissingNode()) {
      out.append("null");
    } else if (node.isObject()) {
      TreeMap<String, JsonNode> sorted = new TreeMap<>();
      for (Map.Entry<String, JsonNode> entry : node.properties()) {
        sorted.put(entry.getKey(), entry.getValue());
      }
      out.append('{');
      boolean first = true;
      for (Map.Entry<String, JsonNode> entry : sorted.entrySet()) {
        if (!first) {
          out.append(',');
        }
        first = false;
        out.append('"').append(entry.getKey()).append("\":");
        write(entry.getValue(), out);
      }
      out.append('}');
    } else if (node.isArray()) {
      out.append('[');
      for (int i = 0; i < node.size(); i++) {
        if (i > 0) {
          out.append(',');
        }
        write(node.get(i), out);
      }
      out.append(']');
    } else {
      out.append(node.toString());
    }
  }

  /**
   * 공고가 걸친 지역 5자리 코드(지역 색인). 위치(locations)의 법정동코드 앞 5자리를 모아요. 시도까지만 아는 위치는 시도 단위 코드(xx000)로 넣어, 시도
   * 검색(11 또는 11000 → 11로 시작하는 모든 코드)에는 나오고 다른 시군구 검색에는 나오지 않게 해요(2026-10-20 결정). 위치가 없으면 payload의
   * 지역 코드를 써요. 보류한 위치나 지역 코드(heldItems의 /locations/{i}·/locations/{i}/regionCode)는 확정 값이 아니라 쓰지
   * 않아요.
   */
  public static List<String> sigunguCodes(ExtractionEvent event) {
    TreeSet<String> codes = new TreeSet<>();
    if (event.notice() != null) {
      JsonNode locations = event.notice().path("locations");
      for (int i = 0; i < locations.size(); i++) {
        JsonNode code = regionCode(event.heldItems(), locations, i);
        if (code.isString() && code.asString().matches("\\d{10}")) {
          String sigungu = code.asString().substring(0, 5);
          if (!sigungu.startsWith("00")) {
            codes.add(sigungu);
          }
        }
      }
    }
    if (codes.isEmpty() && event.regionCode() != null && event.regionCode().matches("\\d{5}")) {
      codes.add(event.regionCode());
    }
    return List.copyOf(codes);
  }

  /**
   * 전국 대상 공고인지: 위치의 원문 지역 표현이 「전국」(「전국 단위」「전국(…)」 포함)인 위치가 있고, 지역 코드가 정해진 위치는 하나도 없을 때만 true. 원문의
   * 「전국」은 모집 지역이 아닌 경우가 많아요(실측: 「전국 소재 주택」(무주택 판정), 「전국(국내)에 거주하는 … 에게 공급」(양산시 단지 매각의 신청 자격)). 특정
   * 단지가 있는 공고는 신청 자격이 전국이어도 그 단지 지역 공고예요. 위치가 없는 공고도 전국으로 보지 않아요(주택 목록이 첨부에만 있는 「대구경북지역」 공고).
   *
   * <p>위치의 지역을 하나라도 보류했으면 그 위치가 어느 지역인지 몰라 전국으로 보지 않아요(모든 지역 검색에 잘못 나오지 않게).
   */
  public static boolean nationwide(ExtractionEvent event) {
    if (event.notice() == null) {
      return false;
    }
    boolean said = false;
    JsonNode locations = event.notice().path("locations");
    for (int i = 0; i < locations.size(); i++) {
      if (held(event.heldItems(), "/locations/" + i + "/regionCode")
          || held(event.heldItems(), "/locations/" + i + "/region")) {
        return false;
      }
      JsonNode location = locations.get(i);
      if (location.path("regionCode").isString()) {
        return false;
      }
      String region = location.path("region").asString("").strip();
      said |= region.matches("전국(\\s.*|\\(.*|단위.*)?");
    }
    return said;
  }

  /**
   * 지역 색인: 지역 5자리 → 대상 지역 전체인지. 위치 종류 AREA(공고 대상 지역, 예: 「대구경북지역」 → 대구·경북)로 정한 코드는 true라 그 아래 시군구
   * 검색에도 나와요. 특정 주택 위치의 코드는 false(시군구를 몰라 시도 단위가 됐으면 시도 검색에만 나옴).
   */
  public static Map<String, Boolean> regions(ExtractionEvent event) {
    Map<String, Boolean> regions = new TreeMap<>();
    for (String code : sigunguCodes(event)) {
      regions.put(code, false);
    }
    if (event.notice() != null) {
      JsonNode locations = event.notice().path("locations");
      for (int i = 0; i < locations.size(); i++) {
        JsonNode location = locations.get(i);
        JsonNode code = regionCode(event.heldItems(), locations, i);
        if ("AREA".equals(location.path("kind").asString(""))
            && code.isString()
            && code.asString().matches("\\d{10}")
            && !code.asString().startsWith("00")) {
          regions.put(code.asString().substring(0, 5), true);
        }
      }
    }
    return regions;
  }

  /** i번째 위치의 지역 코드. 위치나 지역 코드를 보류했으면 없는 값(MissingNode)이에요. */
  private static JsonNode regionCode(JsonNode heldItems, JsonNode locations, int i) {
    return held(heldItems, "/locations/" + i + "/regionCode")
        ? MissingNode.getInstance()
        : locations.get(i).path("regionCode");
  }

  /**
   * 지역 5자리 목록 → 대표 지역 하나 (이벤트 regionCode 규칙과 같음): 하나면 그 코드, 한 시도 안이면 그 시도의 xx000, 여러 시도이거나 없으면
   * null.
   */
  public static String representativeRegion(List<String> codes) {
    if (codes.isEmpty()) return null;
    if (codes.size() == 1) return codes.getFirst();
    Set<String> sido = new TreeSet<>();
    for (String code : codes) sido.add(code.substring(0, 2));
    return sido.size() == 1 ? sido.iterator().next() + "000" : null;
  }

  /** 접수 상태 계산용 구간 (원문 일정의 시각·보류 구간까지 반영). */
  public static List<Window> statusWindows(ExtractionEvent event) {
    return NoticeProjection.statusWindows(
        event.notice(), event.reviewStatus() == ReviewStatus.APPROVED);
  }

  /** 원문에 상시 모집이 명시된 접수 일정(kinds에 APPLICATION, applicationMode=ROLLING)이 있는지. 보류한 일정은 판정에 쓰지 않아요. */
  public static boolean rolling(ExtractionEvent event) {
    return NoticeProjection.rolling(event.notice(), event.reviewStatus() == ReviewStatus.APPROVED);
  }

  /** 보류 범위와 양방향으로 겹치는지. 하위 필드를 보류한 항목도 사용하지 않아요. */
  static boolean held(JsonNode heldItems, String pointer) {
    for (JsonNode item : heldItems) {
      String target = item.path("target").asString("");
      if (!target.isEmpty()
          && (pointer.equals(target)
              || pointer.startsWith(target + "/")
              || target.startsWith(pointer + "/"))) {
        return true;
      }
    }
    return false;
  }

  /**
   * 원본 글의 종류와 정정 관계. 수집기가 넣어 준 값(notice.sourceReferences 중 이 원본 글)을 그대로 써요. 상세가 없거나 못 찾으면 일반 공고로
   * 봐요.
   *
   * @param kind NOTICE, CORRECTION(정정 공고), FOLLOW_UP(후속 안내)
   * @param supersedesPostId 정정·후속 안내가 가리키는 원래 공고의 원본 글 ID
   * @param sourceTitle 원본 글 제목 (없으면 null)
   * @param detailUrl 원문 링크 (없으면 null)
   * @param postedOn 게시일 (없으면 null)
   */
  public record Source(
      String kind,
      UUID supersedesPostId,
      String sourceTitle,
      String detailUrl,
      LocalDate postedOn) {

    public static final String NOTICE = "NOTICE";
    public static final String CORRECTION = "CORRECTION";
    public static final String FOLLOW_UP = "FOLLOW_UP";

    public boolean correction() {
      return CORRECTION.equals(kind) && supersedesPostId != null;
    }

    public boolean followUp() {
      return FOLLOW_UP.equals(kind) && supersedesPostId != null;
    }

    /** 정정·후속 안내인데 원래 공고를 가리키지 않음 (계약 UNLINKED_RELATED_NOTICE). 일반 공고로 공개하지 않고 보류해요. */
    public boolean unlinked() {
      return !NOTICE.equals(kind) && supersedesPostId == null;
    }
  }

  public static Source source(ExtractionEvent event) {
    if (event.notice() != null) {
      for (JsonNode reference : event.notice().path("sourceReferences")) {
        if (event
            .rawPostId()
            .toString()
            .equalsIgnoreCase(reference.path("rawPostId").asString(""))) {
          JsonNode supersedes = reference.path("supersedesPostId");
          return new Source(
              reference.path("kind").asString(Source.NOTICE),
              supersedes.isString() ? UUID.fromString(supersedes.asString()) : null,
              textOrNull(reference, "sourceTitle"),
              textOrNull(reference, "detailUrl"),
              date(reference, "postedOn"));
        }
      }
    }
    return new Source(Source.NOTICE, null, null, null, null);
  }

  /**
   * 후속 안내의 일정 (상세 공고의 schedules에서 보류한 일정을 뺀 것). 후속 안내는 일정만 저장하고 보류 항목(heldItems)은 두지 않아서, 그대로 두면
   * 보류한 일정이 확정처럼 보였어요(2026-11-10 코드 검토). 본 공고 상세도 보류한 일정은 보여 주지 않아요.
   */
  public static JsonNode schedules(ExtractionEvent event) {
    var out = tools.jackson.databind.node.JsonNodeFactory.instance.arrayNode();
    JsonNode schedules = event.notice() == null ? null : event.notice().path("schedules");
    if (schedules == null || !schedules.isArray()) {
      return out;
    }
    for (int i = 0; i < schedules.size(); i++) {
      if (!held(event.heldItems(), "/schedules/" + i)) {
        out.add(schedules.get(i));
      }
    }
    return out;
  }

  /** 상세 공고의 공급 기관·공급 유형 (목록 표시·필터용). */
  public static String publisher(ExtractionEvent event) {
    return noticeText(event, "publisher");
  }

  /** area에 보낼 위치 목록 (상세 공고의 locations). */
  public static List<NoticeLocationsChanged.Location> locations(ExtractionEvent event) {
    return event.notice() == null
        ? new ArrayList<>()
        : locations(event.notice(), event.heldItems());
  }

  /** 저장해 둔 스냅샷의 위치 목록 (보충 발행용). 보류 항목은 스냅샷의 quality.heldItems를 봐요. */
  public static List<NoticeLocationsChanged.Location> locations(JsonNode snapshot) {
    return locations(snapshot, snapshot.path("quality").path("heldItems"));
  }

  /**
   * 위치 목록. 보류한 위치(/locations/{i} 전체나 주소·이름)는 빼고, 지역 코드만 보류했으면 코드 없이 보내요. 미확정 위치로 지역 점수를 계산하지 않게 해요.
   */
  private static List<NoticeLocationsChanged.Location> locations(
      JsonNode snapshot, JsonNode heldItems) {
    List<NoticeLocationsChanged.Location> locations = new ArrayList<>();
    JsonNode all = snapshot.path("locations");
    for (int i = 0; i < all.size(); i++) {
      JsonNode location = all.get(i);
      String id = textOrNull(location, "id");
      if (id == null || "AREA".equals(location.path("kind").asString(""))) {
        continue; // 대상 지역(AREA)은 주택 위치가 아니라 생활·상업 점수를 계산하지 않아요
      }
      String at = "/locations/" + i;
      if (coversWhole(heldItems, at)
          || held(heldItems, at + "/address")
          || held(heldItems, at + "/complexName")
          || held(heldItems, at + "/buildingName")) {
        continue;
      }
      String name = textOrNull(location, "complexName");
      locations.add(
          new NoticeLocationsChanged.Location(
              id,
              location.path("kind").asString("UNKNOWN"),
              held(heldItems, at + "/regionCode") ? null : textOrNull(location, "regionCode"),
              textOrNull(location, "address"),
              name != null ? name : textOrNull(location, "buildingName")));
    }
    return locations;
  }

  /** 보류 범위가 pointer 자체이거나 그 위(상위 섹션)인지. 하위 칸 하나만 보류한 경우는 포함하지 않아요. */
  private static boolean coversWhole(JsonNode heldItems, String pointer) {
    for (JsonNode item : heldItems) {
      String target = item.path("target").asString("");
      if (!target.isEmpty() && (pointer.equals(target) || pointer.startsWith(target + "/"))) {
        return true;
      }
    }
    return false;
  }

  /**
   * 지역 점수를 저장하고 보여 줄 위치 ID. area에 보내는 위치(locations(snapshot))와 같은 규칙이라, 보류한 위치(위치 전체나 주소·이름)는 빠져요.
   * 이전 버전에서 계산한 점수가 남아 있어도 지금 보류한 위치의 점수는 보여 주지 않아요.
   */
  public static Set<String> locationIds(JsonNode snapshot) {
    Set<String> ids = new java.util.HashSet<>();
    for (NoticeLocationsChanged.Location location : locations(snapshot)) {
      ids.add(location.locationId());
    }
    return ids;
  }

  /** 결과에 공고문 PDF가 있는지 (기준 출처 고르기). */
  public static boolean hasPdf(ExtractionEvent event) {
    if (event.notice() == null) {
      return false;
    }
    for (JsonNode document : event.notice().path("documents")) {
      if ("PDF".equals(document.path("kind").asString(""))) {
        return true;
      }
    }
    return false;
  }

  /** 위치의 단지·건물 이름 (같은 공고 판별용). 보류한 위치는 빼요. */
  public static Set<String> complexNames(ExtractionEvent event) {
    Set<String> names = new TreeSet<>();
    if (event.notice() == null) {
      return names;
    }
    JsonNode all = event.notice().path("locations");
    for (int i = 0; i < all.size(); i++) {
      if (held(event.heldItems(), "/locations/" + i)) {
        continue;
      }
      String name = textOrNull(all.get(i), "complexName");
      name = name != null ? name : textOrNull(all.get(i), "buildingName");
      if (name != null) {
        names.add(name);
      }
    }
    return names;
  }

  /**
   * 공고일 (상세 공고의 notice.announcedOn). 없거나 날짜가 아니거나 보류한 칸이면(부분 게시, 2026-10-20) null. 같은 공고 후보 찾기에 쓰므로
   * 보류한 공고일로 후보를 만들지 않아요.
   */
  public static LocalDate announcedOn(ExtractionEvent event) {
    if (event.notice() == null || heldNoticeField(event, "announcedOn")) {
      return null;
    }
    return date(event.notice().path("notice"), "announcedOn");
  }

  /** 공급 유형 (목록 표시·필터용). 보류한 칸이면 null. */
  public static String supplyType(ExtractionEvent event) {
    return heldNoticeField(event, "supplyType") ? null : noticeText(event, "supplyType");
  }

  /** 공고 기본 정보 칸(/notice/{name})이 보류됐는지. 칸 자체나 그 안을 보류해도 그 칸은 쓰지 않아요. */
  static boolean heldNoticeField(ExtractionEvent event, String name) {
    String pointer = "/notice/" + name;
    for (JsonNode item : event.heldItems()) {
      String target = item.path("target").asString("");
      if (target.equals(pointer)
          || target.startsWith(pointer + "/")
          || pointer.startsWith(target + "/")) {
        return true;
      }
    }
    return false;
  }

  private static String noticeText(ExtractionEvent event, String name) {
    if (event.notice() == null) {
      return null;
    }
    JsonNode value = event.notice().path("notice").path(name);
    return value.isString() && !value.asString().isBlank() ? value.asString() : null;
  }

  private static String textOrNull(JsonNode node, String name) {
    JsonNode value = node.path(name);
    return value.isString() && !value.asString().isBlank() ? value.asString() : null;
  }

  private static LocalDate date(JsonNode node, String name) {
    JsonNode value = node.path(name);
    if (!value.isString()) {
      return null;
    }
    try {
      return LocalDate.parse(value.asString());
    } catch (DateTimeParseException e) {
      return null;
    }
  }

  private static boolean same(JsonNode a, JsonNode b) {
    return Objects.equals(canonical(a), canonical(b));
  }
}
