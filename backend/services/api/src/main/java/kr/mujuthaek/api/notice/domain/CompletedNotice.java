package kr.mujuthaek.api.notice.domain;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;
import tools.jackson.databind.JsonNode;

/**
 * extraction.completed payload에서 notice가 쓰는 값 (contracts/events/extraction.completed.v1.json).
 *
 * <p>글 종류(kind)와 원래 공고(supersedesPostId)는 상세 notice의 sourceReferences에서 이 원본(rawPostId)을 가리키는 항목으로
 * 봐요. 상세가 없으면(IN_REVIEW에서 빠질 수 있음) 모집공고로 봐요.
 *
 * @param payload 받은 payload 전체 (상세 화면용으로 그대로 저장)
 */
public record CompletedNotice(
    UUID rawPostId,
    int rawVersion,
    String field,
    String kind,
    UUID supersedesPostId,
    String reviewStatus,
    String title,
    String provider,
    String supplyTypeText,
    NoticeType noticeType,
    String regionCode,
    LocalDate applyStart,
    LocalDate applyEnd,
    LocalDate postedOn,
    String summary,
    String detailUrl,
    boolean reprocess,
    JsonNode payload) {

  /** notice가 받는 분야 (정책·창업지원은 benefit이 받아요). */
  public boolean isNoticeField() {
    return "HOUSING".equals(field) || "BUSINESS_SPACE".equals(field);
  }

  /** 공개해도 되는 결과인지 (검수 대기면 이전 공개 버전을 유지해요). */
  public boolean publishable() {
    return !"IN_REVIEW".equals(reviewStatus);
  }

  public boolean approved() {
    return "APPROVED".equals(reviewStatus);
  }

  /** 앞 버전과 비교해 바뀐 목록 값 (API 필드 이름). 정정 이력에 보여줘요. */
  public List<String> changedFrom(CompletedNotice before) {
    List<String> changed = new ArrayList<>();
    addIf(changed, "title", before.title, title);
    addIf(changed, "provider", before.provider, provider);
    addIf(changed, "noticeType", before.noticeType, noticeType);
    addIf(changed, "regionCode", before.regionCode, regionCode);
    addIf(changed, "applyStart", before.applyStart, applyStart);
    addIf(changed, "applyEnd", before.applyEnd, applyEnd);
    addIf(changed, "summaryText", before.summary, summary);
    return changed;
  }

  private static void addIf(List<String> changed, String name, Object before, Object after) {
    if (!Objects.equals(before, after)) {
      changed.add(name);
    }
  }

  public static CompletedNotice from(JsonNode p) {
    UUID rawPostId = UUID.fromString(p.get("rawPostId").asString());
    String field = p.get("field").asString();
    JsonNode detail = p.path("notice");
    JsonNode source = sourceReference(detail, rawPostId);
    JsonNode held = p.path("heldItems");
    // 원문 확인 전까지 보류한 칸은 목록 값으로 쓰지 않아요(틀린 값보다 빈 값이 나아요)
    String supplyType =
        held(held, "/notice/supplyType") ? null : text(detail.path("notice").path("supplyType"));
    LocalDate announced =
        held(held, "/notice/announcedOn") ? null : date(detail.path("notice").path("announcedOn"));
    return new CompletedNotice(
        rawPostId,
        p.get("rawVersion").asInt(),
        field,
        source.path("kind").isMissingNode() ? "NOTICE" : source.path("kind").asString(),
        uuid(source.path("supersedesPostId")),
        p.get("reviewStatus").asString(),
        p.get("title").asString(),
        text(p.path("provider")),
        supplyType,
        NoticeType.fromSupplyType(supplyType, field),
        text(p.path("regionCode")),
        applyPeriod(p)[0],
        applyPeriod(p)[1],
        announced != null ? announced : date(source.path("postedOn")),
        text(p.path("summary")),
        text(source.path("detailUrl")),
        p.path("reprocess").asBoolean(false),
        p);
  }

  private static JsonNode sourceReference(JsonNode detail, UUID rawPostId) {
    for (JsonNode ref : detail.path("sourceReferences")) {
      if (rawPostId.toString().equals(ref.path("rawPostId").asString(null))) {
        return ref;
      }
    }
    return detail.path("sourceReferences").path(0);
  }

  /** 보류 범위가 이 칸이거나 그 위·아래와 겹치는지. */
  private static boolean held(JsonNode heldItems, String pointer) {
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

  private static String text(JsonNode node) {
    return node.isMissingNode() || node.isNull() ? null : node.asString();
  }

  /**
   * 공고의 접수 기간 [시작, 끝]. 공고 전체 접수 일정이 하나면 그 기간(schedule)이고, 순위·대상별로 여러 개라 schedule이 없으면 검증된 접수
   * 구간(applicationWindows)의 가장 이른 시작 ~ 가장 늦은 끝이에요. 끝을 모르는 구간이 하나라도 있으면 끝은 null이에요(2026-10-26 원문 대조:
   * 1·2순위 접수가 따로 있는 공고는 기간이 비어 「일정 확인」으로 보였음). 확인 전까지 보류한 접수 일정은 접수 구간에서 빠지므로, 원문 접수 일정 수보다 구간이 적으면
   * 더 늦은 접수가 있을 수 있어 끝은 null이에요(2026-11-10 코드 검토: 보류한 2순위 10/05~10/07을 빼고 마감 10/03으로 보여 D-day·마감
   * 알림이 앞당겨졌음. 접수 상태는 statusWindows가 보류 구간을 날짜 모르는 구간으로 넣어 이미 맞았음).
   */
  static LocalDate[] applyPeriod(JsonNode p) {
    LocalDate start = date(p.path("schedule").path("applyStartOn"));
    LocalDate end = date(p.path("schedule").path("applyEndOn"));
    JsonNode windows = p.path("applicationWindows");
    // 원문 접수 일정이 여럿이면 공고 전체 일정(schedule) 하나로 정하지 않아요: 범위 미정·위치·공급 묶음 범위의 다른 접수 일정이 더 늦을 수 있는데
    // 전체 일정만 보고 마감일을 앞당겼어요(2026-11-10 재검토. 접수 상태는 모든 접수 일정으로 계산해 이미 맞았음)
    boolean several = applicationSchedules(p.path("notice").path("schedules")) > 1;
    if (several && windows.isArray() && !windows.isEmpty()) {
      start = null;
      end = null;
    } else if (start != null || end != null || !windows.isArray() || windows.isEmpty()) {
      return new LocalDate[] {start, end};
    }
    boolean endKnown = windows.size() >= applicationSchedules(p.path("notice").path("schedules"));
    for (JsonNode w : windows) {
      LocalDate s = date(w.path("applyStartOn"));
      LocalDate e = date(w.path("applyEndOn"));
      if (s != null && (start == null || s.isBefore(start))) {
        start = s;
      }
      if (e == null) {
        endKnown = false;
      } else if (end == null || e.isAfter(end)) {
        end = e;
      }
    }
    return new LocalDate[] {start, endKnown ? end : null};
  }

  /** 원문 일정 중 접수(APPLICATION) 일정 수 (보류·검수 대상 포함). */
  private static int applicationSchedules(JsonNode schedules) {
    int count = 0;
    for (JsonNode s : schedules) {
      for (JsonNode kind : s.path("kinds")) {
        if ("APPLICATION".equals(kind.asString())) {
          count++;
          break;
        }
      }
    }
    return count;
  }

  private static LocalDate date(JsonNode node) {
    String value = text(node);
    return value == null ? null : LocalDate.parse(value);
  }

  private static UUID uuid(JsonNode node) {
    String value = text(node);
    return value == null ? null : UUID.fromString(value);
  }
}
