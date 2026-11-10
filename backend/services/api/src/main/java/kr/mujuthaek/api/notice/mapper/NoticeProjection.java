package kr.mujuthaek.api.notice.mapper;

import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import kr.mujuthaek.api.notice.domain.ApplicationStatusCalculator.Window;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.JsonNodeFactory;
import tools.jackson.databind.node.ObjectNode;

/** contracts/tools/validate_contracts.py의 일정·지역 투영. 공유 입력 사례로 두 언어의 결과를 대조해요. */
public final class NoticeProjection {
  private static final JsonNodeFactory NODES = JsonNodeFactory.instance;
  private static final ZoneId KOREA = ZoneId.of("Asia/Seoul");

  private NoticeProjection() {}

  /**
   * 이벤트 regionCode(5자리 = 시도 2 + 시군구 3)의 정답 (계약 event_region_code와 같은 규칙, 2026-10-20). 서비스는 앞 5자리만
   * 써요. 모든 위치의 앞 5자리가 하나면 그 코드(시도까지만 아는 위치면 xx000), 여러 시군구지만 같은 시도면 그 시도의 xx000, 여러 시도·코드 없는 위치·위치
   * 없음이면 null. 보류한 위치·지역 코드(quality.heldItems)는 확정 값이 아니라 코드 없는 위치로 봐요(2026-10-21).
   */
  public static String regionCode(JsonNode detail) {
    Set<String> codes = new TreeSet<>();
    JsonNode locations = detail.path("locations");
    if (locations.isEmpty()) return null;
    JsonNode held = detail.path("quality").path("heldItems");
    for (int i = 0; i < locations.size(); i++) {
      String code =
          NoticeContent.held(held, "/locations/" + i + "/regionCode")
              ? null
              : locations.get(i).path("regionCode").asString(null);
      if (code == null || code.length() != 10 || !regionCodeValid(code.substring(0, 5)))
        return null;
      codes.add(code.substring(0, 5));
    }
    if (codes.size() == 1) return codes.iterator().next();
    Set<String> sido = new TreeSet<>();
    for (String code : codes) sido.add(code.substring(0, 2));
    return sido.size() == 1 ? sido.iterator().next() + "000" : null;
  }

  static boolean regionCodeValid(String code) {
    if (!code.matches("[0-9]{5}|[0-9]{10}") || code.startsWith("00")) return false;
    if (code.length() == 5) return true; // 시군구 자리 000은 시도 단위(11000 = 서울특별시)
    boolean zero = false;
    for (String part : List.of(code.substring(2, 5), code.substring(5, 8), code.substring(8))) {
      if (part.matches("0+")) zero = true;
      else if (zero) return false;
    }
    return true;
  }

  /** 매개변수 이름을 풀어요. 잘못된 % 인코딩이면 원래 글자로 봐요(그 URL 전체를 검사에서 빼지 않게, 리뷰 2026-10-22). */
  private static String decodeOrRaw(String raw) {
    try {
      return URLDecoder.decode(raw, StandardCharsets.UTF_8);
    } catch (IllegalArgumentException e) {
      return raw;
    }
  }

  static boolean privateUrl(String value) {
    try {
      URI uri = URI.create(value);
      if (uri.getUserInfo() != null) return true;
      for (String part :
          List.of(
              uri.getRawQuery() == null ? "" : uri.getRawQuery(),
              uri.getRawFragment() == null ? "" : uri.getRawFragment())) {
        for (String pair : part.split("&")) {
          String key =
              decodeOrRaw(pair.split("=", 2)[0])
                  .toLowerCase(java.util.Locale.ROOT)
                  .replace("_", "")
                  .replace("-", "");
          if (key.equals("key")
              || List.of(
                      "servicekey",
                      "apikey",
                      "authkey",
                      "accesstoken",
                      "token",
                      "signature",
                      "credential")
                  .stream()
                  .anyMatch(key::contains)) return true;
        }
      }
      return false;
    } catch (IllegalArgumentException e) {
      // 계약 검사기(private_url)와 같게: 해석할 수 없는 주소는 이 검사로 막지 않아요. 한글 파일 이름처럼 인코딩하지 않은 글자가 있으면
      // URI.create가 실패하는데, 이를 비공개 주소로 보면 계약을 통과한 이벤트가 실패 큐로 가요. serviceKey= 같은 값은 글자 검사가 따로 막아요
      return false;
    }
  }

  private static boolean blocked(JsonNode detail, int index, boolean approved) {
    return blocked(detail, index, approved, false);
  }

  /**
   * 접수 기간에서 뺄 일정. 보류와 겹치면 빼고, 검수 이슈는 그 일정 자신이나 그 안을 가리킬 때만 빼요(계약 application_items). 표시 메모로는 빼지
   * 않아요: 메모는 값이 틀렸다는 신호가 아닌데, 인용 하나가 짧다는 메모로 하나뿐인 접수 일정이 빠져 마감일을 잃었어요(2026-11-10 재검토). withNotes는
   * 바꾸기 전 규칙(메모로도 뺌)으로 만든 이벤트를 받을 때만 써요(NoticeContract).
   */
  private static boolean blocked(JsonNode detail, int index, boolean approved, boolean withNotes) {
    String pointer = "/schedules/" + index;
    JsonNode quality = detail.path("quality");
    if (NoticeContent.held(quality.path("heldItems"), pointer)) return true;
    if (!approved
        && (within(quality.path("reviewIssues"), pointer)
            || (withNotes && within(quality.path("notes"), pointer)))) return true;
    return false;
  }

  private static boolean within(JsonNode entries, String pointer) {
    for (JsonNode entry : entries) {
      String target = entry.path("target").asString("");
      if (target.equals(pointer) || target.startsWith(pointer + "/")) return true;
    }
    return false;
  }

  /** 신청 방법의 정해진 순서 (계약 notice-common applicationChannel, 2026-10-23). */
  public static final List<String> CHANNELS = List.of("ONLINE", "ONSITE", "EMAIL", "MAIL", "FAX");

  /** 정해진 신청 방법만 정해진 순서로. 2026-10-23 이전 저장본의 자유 글자(「인터넷」 등)는 빼요. */
  public static List<String> channels(JsonNode values) {
    Set<String> found = new java.util.HashSet<>();
    for (JsonNode v : values) found.add(v.asString(""));
    return CHANNELS.stream().filter(found::contains).toList();
  }

  /**
   * 공고 전체 신청 방법의 정답 (계약 application_channels와 같은 규칙): 신청(APPLICATION) 일정들의 channels를 합쳐 정해진 순서로. 보류
   * 여부와 상관없이 모든 신청 일정을 봐요.
   */
  public static List<String> applicationChannels(JsonNode detail) {
    Set<String> found = new java.util.HashSet<>();
    boolean anyApplication = false;
    for (JsonNode s : detail.path("schedules"))
      if (application(s)) {
        anyApplication = true;
        found.addAll(channels(s.path("channels")));
      }
    // 신청 일정이 없으면(계약으로 바로 신청받는 선착순 공고) 계약 일정들의 방법을 합쳐요 (Python 계약 검사기와 같게)
    if (!anyApplication)
      for (JsonNode s : detail.path("schedules"))
        if (hasKind(s, "CONTRACT")) found.addAll(channels(s.path("channels")));
    return CHANNELS.stream().filter(found::contains).toList();
  }

  private static boolean application(JsonNode item) {
    return hasKind(item, "APPLICATION");
  }

  private static boolean hasKind(JsonNode item, String kind) {
    for (JsonNode k : item.path("kinds")) if (kind.equals(k.asString())) return true;
    return false;
  }

  private static List<JsonNode> items(JsonNode detail, boolean approved) {
    return items(detail, approved, false);
  }

  private static List<JsonNode> items(JsonNode detail, boolean approved, boolean withNotes) {
    List<JsonNode> result = new ArrayList<>();
    JsonNode schedules = detail.path("schedules");
    for (int i = 0; i < schedules.size(); i++) {
      if (application(schedules.get(i)) && !blocked(detail, i, approved, withNotes))
        result.add(schedules.get(i));
    }
    return result;
  }

  public static boolean rolling(JsonNode detail, boolean approved) {
    return items(detail, approved).stream()
        .anyMatch(s -> "ROLLING".equals(s.path("applicationMode").asString("")));
  }

  public static LocalDate day(JsonNode value) {
    if (value.isNull()
        || value.isMissingNode()
        || "MONTH".equals(value.path("precision").asString())) return null;
    return "DAY".equals(value.path("precision").asString())
        ? LocalDate.parse(value.path("value").asString())
        : OffsetDateTime.parse(value.path("value").asString())
            .atZoneSameInstant(KOREA)
            .toLocalDate();
  }

  public static JsonNode schedule(JsonNode detail, boolean approved) {
    return schedule(detail, approved, false);
  }

  /** 바꾸기 전 규칙(표시 메모로도 일정을 뺌)으로 만든 공고 전체 접수 기간. 그 규칙으로 만든 이벤트를 받을 때만 써요(NoticeContract). */
  public static JsonNode legacySchedule(JsonNode detail, boolean approved) {
    return schedule(detail, approved, true);
  }

  private static JsonNode schedule(JsonNode detail, boolean approved, boolean withNotes) {
    List<JsonNode> whole = new ArrayList<>();
    for (JsonNode s : detail.path("schedules")) {
      if (application(s)
          && "NOTICE".equals(s.path("scope").path("level").asString())
          && "RESOLVED".equals(s.path("scope").path("resolution").asString())) whole.add(s);
    }
    if (whole.size() != 1 || !items(detail, approved, withNotes).contains(whole.getFirst()))
      return NODES.nullNode();
    LocalDate start = day(whole.getFirst().path("startsAt")),
        end = day(whole.getFirst().path("endsAt"));
    return start == null && end == null ? NODES.nullNode() : dates(NODES.objectNode(), start, end);
  }

  /**
   * 접수 상태 계산용 구간. 원문 일정에서 바로 만들어 시각을 잃지 않아요(「10/30 17:00까지」는 17시까지만 접수 중). 확인 전까지 보류한 접수 일정은 빼지 않고
   * 날짜 모르는 구간으로 넣어, 끝난 구간만 보고 마감으로 확정하지 않게 해요(남은 접수가 있을 수 있음).
   */
  public static List<Window> statusWindows(JsonNode detail, boolean approved) {
    List<Window> result = new ArrayList<>();
    JsonNode schedules = detail.path("schedules");
    for (int i = 0; i < schedules.size(); i++) {
      JsonNode s = schedules.get(i);
      if (!application(s)) continue;
      if (blocked(detail, i, approved)) {
        result.add(new Window(null, null));
        continue;
      }
      result.add(
          new Window(
              day(s.path("startsAt")),
              day(s.path("endsAt")),
              instant(s.path("startsAt")),
              instant(s.path("endsAt"))));
    }
    return result;
  }

  /** 시각까지 적힌 일정 값이면 그 시각, 날짜·월만 있으면 null. */
  static Instant instant(JsonNode value) {
    if (value.isNull() || value.isMissingNode()) return null;
    String precision = value.path("precision").asString("");
    if ("DAY".equals(precision) || "MONTH".equals(precision)) return null;
    return OffsetDateTime.parse(value.path("value").asString()).toInstant();
  }

  public static ArrayNode windows(JsonNode detail, boolean approved) {
    return windows(detail, approved, false);
  }

  /** 바꾸기 전 규칙(표시 메모로도 일정을 뺌)으로 만든 접수 구간. 그 규칙으로 만든 이벤트를 받을 때만 써요(NoticeContract). */
  public static ArrayNode legacyWindows(JsonNode detail, boolean approved) {
    return windows(detail, approved, true);
  }

  private static ArrayNode windows(JsonNode detail, boolean approved, boolean withNotes) {
    ArrayNode result = NODES.arrayNode();
    for (JsonNode s : items(detail, approved, withNotes)) {
      ObjectNode window = dates(NODES.objectNode(), day(s.path("startsAt")), day(s.path("endsAt")));
      window.set("scheduleId", s.path("id"));
      window.set("label", s.path("rawLabel"));
      window.set("priorityRank", s.path("priorityRank"));
      window.set("targetGroups", s.path("scope").path("targetGroups"));
      window.set("scopeDescription", s.path("scope").path("description"));
      result.add(window);
    }
    return result;
  }

  private static ObjectNode dates(ObjectNode result, LocalDate start, LocalDate end) {
    result.put("applyStartOn", start == null ? null : start.toString());
    result.put("applyEndOn", end == null ? null : end.toString());
    return result;
  }
}
