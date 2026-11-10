package kr.mujuthaek.api.notice.mapper;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.ApplicationEmail;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.AreaSummary;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.Condition;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.Evidence;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.FileLink;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.FollowUp;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.Guidance;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.HeldItem;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.Place;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.RequiredDocument;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.Schedule;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.SelectionRule;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.Site;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.Summary;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.TimeRange;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.UnitType;
import kr.mujuthaek.api.notice.dto.response.NoticeUnitResponse;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.JsonNodeFactory;

/**
 * 저장한 extraction.completed payload(상세 notice: contracts/schemas/extracted-notice.v1.json)에서 상세 응답
 * 묶음을 만들어요.
 *
 * <p>칸이 없으면 빈 목록·null로 둬요 (검수 대기 등으로 상세가 빠진 버전도 있어요).
 *
 * <p>원문 확인 전까지 보류한 항목(quality.heldItems)은 보여 주지 않아요: 그 일정·주택형·호·위치·첨부를 빼고, 위치 칸 하나만 보류했으면 그 칸만 비워요.
 * 공급 묶음의 수량이나 가격만 보류했으면 그 값만 비우고 주택형·호는 보여 줘요. 보류한 자격 조건은 확인 필요(inReview)로 표시하고 근거는 비워요. 무엇을 뺐는지는
 * heldItems로 알려요.
 *
 * <p>근거(evidence)는 항목의 evidenceIds로 상세의 evidence에서 찾아 인용·쪽·문서 이름을 붙여요. 쪽은 근거 위치가 PDF 쪽(PDF_PAGE)일
 * 때만 있어요.
 */
public final class NoticeDetailMapper {

  private NoticeDetailMapper() {}

  public static NoticeDetailResponse map(
      NoticeDetailResponse.Header header,
      JsonNode payload,
      List<AreaSummary> areaSummaries,
      List<FollowUp> followUps,
      int version,
      boolean reviewed,
      OffsetDateTime updatedAt,
      LocalDate today) {
    JsonNode detail = payload.path("notice");
    List<UnitType> unitTypes = unitTypes(detail);
    return new NoticeDetailResponse(
        header,
        summary(payload, detail, unitTypes),
        schedules(detail, today),
        sites(detail),
        unitTypes,
        conditions(payload, detail),
        requiredDocuments(detail),
        selectionRules(detail),
        guidance(detail),
        files(detail),
        heldItems(detail),
        areaSummaries,
        followUps,
        hasUnits(detail),
        version,
        reviewed,
        updatedAt);
  }

  static Summary summary(JsonNode payload, JsonNode detail, List<UnitType> unitTypes) {
    BigDecimal min = null;
    BigDecimal max = null;
    for (UnitType t : unitTypes) {
      if (t.exclusiveM2() != null) {
        min = min == null || t.exclusiveM2().compareTo(min) < 0 ? t.exclusiveM2() : min;
        max = max == null || t.exclusiveM2().compareTo(max) > 0 ? t.exclusiveM2() : max;
      }
    }
    boolean countsHeld = held(detail, "/notice/counts");
    Integer total = countsHeld ? null : offered(detail.path("notice").path("counts"));
    // 공고에 적힌 수가 없을 때만 주택형별 합을 써요. 공고에 적힌 수를 보류했거나, 공급 수량을 보류했거나 통째로 뺀 공급 묶음이 있으면
    // 합이 다른 값일 수 있어 쓰지 않아요 (가격만 보류한 묶음은 수량이 확정이라 합에 넣어요)
    if (total == null && !countsHeld && !unitTypes.isEmpty() && !supplyCountsHeld(detail)) {
      total = unitTypes.stream().mapToInt(t -> t.supplyCount() == null ? 0 : t.supplyCount()).sum();
    }
    return new Summary(
        text(payload.path("summary")),
        held(detail, "/notice/targetGroups")
            ? List.of()
            : strings(detail.path("notice").path("targetGroups")),
        total,
        min,
        max,
        applicationChannels(detail));
  }

  /**
   * 공고 전체 신청 방법. 추출이 계산해 보낸 값(notice.applicationChannels)을 쓰고, 그 칸이 없는 이전 저장본은 신청 일정에서 같은 규칙으로
   * 계산해요.
   */
  static List<String> applicationChannels(JsonNode detail) {
    JsonNode given = detail.path("notice").path("applicationChannels");
    return given.isArray()
        ? NoticeProjection.channels(given)
        : NoticeProjection.applicationChannels(detail);
  }

  /** 후속 안내 한 건. schedules는 후속 안내 글의 일정(상세의 schedules와 같은 모양)이에요. */
  public static FollowUp followUp(
      String title, String detailUrl, LocalDate postedOn, JsonNode schedules, LocalDate today) {
    return new FollowUp(
        title,
        detailUrl,
        postedOn,
        schedules(JsonNodeFactory.instance.objectNode().set("schedules", schedules), today));
  }

  static List<Schedule> schedules(JsonNode detail, LocalDate today) {
    Map<String, Evidence> evidence = evidence(detail);
    List<Schedule> out = new ArrayList<>();
    JsonNode all = detail.path("schedules");
    for (int i = 0; i < all.size(); i++) {
      if (held(detail, "/schedules/" + i)) {
        continue;
      }
      JsonNode s = all.get(i);
      String starts = text(s.path("startsAt").path("value"));
      String ends = text(s.path("endsAt").path("value"));
      out.add(
          new Schedule(
              text(s.path("id")),
              text(s.path("rawLabel")),
              strings(s.path("kinds")),
              starts,
              ends,
              text(s.path("description")),
              text(s.path("applicationUrl")),
              NoticeProjection.channels(s.path("channels")),
              places(s.path("places")),
              email(s.path("applicationEmail")),
              times(s.path("dailyHours")),
              times(s.path("breaks")),
              strings(s.path("excludedDays")),
              text(s.path("timeNote")),
              within(today, starts, ends),
              cite(evidence, s.path("evidenceIds"))));
    }
    return out;
  }

  private static List<Place> places(JsonNode array) {
    List<Place> out = new ArrayList<>();
    for (JsonNode p : array) {
      out.add(new Place(text(p.path("name")), text(p.path("address")), text(p.path("detail"))));
    }
    return out;
  }

  private static ApplicationEmail email(JsonNode node) {
    return node.isObject() && text(node.path("address")) != null
        ? new ApplicationEmail(text(node.path("address")), text(node.path("subjectFormat")))
        : null;
  }

  private static List<TimeRange> times(JsonNode array) {
    List<TimeRange> out = new ArrayList<>();
    for (JsonNode t : array) {
      out.add(new TimeRange(text(t.path("start")), text(t.path("end"))));
    }
    return out;
  }

  /** 서류 묶음 순서 (공통 → 해당자 → 본인 방문 → 배우자 대리 → 그 밖의 대리 → 묶음 없음). */
  private static final List<String> DOCUMENT_GROUPS =
      List.of("COMMON", "CONDITIONAL", "DIRECT", "PROXY_SPOUSE", "PROXY_OTHER");

  /** 제출 서류. 보류한 서류(/requiredDocuments/{i})는 빼고, 서류 묶음 순서로 놓아요 (같은 묶음 안은 원문 순서). */
  static List<RequiredDocument> requiredDocuments(JsonNode detail) {
    Map<String, Evidence> evidence = evidence(detail);
    List<RequiredDocument> out = new ArrayList<>();
    JsonNode all = detail.path("requiredDocuments");
    for (int i = 0; i < all.size(); i++) {
      if (held(detail, "/requiredDocuments/" + i)) {
        continue;
      }
      JsonNode d = all.get(i);
      out.add(
          new RequiredDocument(
              text(d.path("id")),
              text(d.path("name")),
              text(d.path("group")),
              text(d.path("appliesTo")),
              text(d.path("submissionTime")),
              d.path("copies").isInt() ? d.path("copies").asInt() : null,
              text(d.path("issuer")),
              text(d.path("description")),
              strings(d.path("scope").path("targetGroups")),
              cite(evidence, d.path("evidenceIds"))));
    }
    out.sort(
        Comparator.comparingInt(
            d -> {
              int order = d.group() == null ? -1 : DOCUMENT_GROUPS.indexOf(d.group());
              return order < 0 ? DOCUMENT_GROUPS.size() : order;
            }));
    return out;
  }

  /** 선정 방식. 보류한 항목(/selectionRules/{i})은 빼고 원문 순서로 놓아요. */
  static List<SelectionRule> selectionRules(JsonNode detail) {
    Map<String, Evidence> evidence = evidence(detail);
    List<SelectionRule> out = new ArrayList<>();
    JsonNode all = detail.path("selectionRules");
    for (int i = 0; i < all.size(); i++) {
      if (held(detail, "/selectionRules/" + i)) {
        continue;
      }
      JsonNode r = all.get(i);
      out.add(
          new SelectionRule(
              text(r.path("id")),
              text(r.path("kind")),
              text(r.path("description")),
              text(r.path("originalText")),
              r.path("priorityRank").isInt() ? r.path("priorityRank").asInt() : null,
              decimal(r.path("points")),
              decimal(r.path("maxPoints")),
              r.path("order").isInt() ? r.path("order").asInt() : null,
              strings(r.path("scope").path("targetGroups")),
              cite(evidence, r.path("evidenceIds"))));
    }
    return out;
  }

  /** 안내. 보류한 항목(/guidance/{i})은 빼고 원문 순서로 놓아요. */
  static List<Guidance> guidance(JsonNode detail) {
    Map<String, Evidence> evidence = evidence(detail);
    List<Guidance> out = new ArrayList<>();
    JsonNode all = detail.path("guidance");
    for (int i = 0; i < all.size(); i++) {
      if (held(detail, "/guidance/" + i)) {
        continue;
      }
      JsonNode g = all.get(i);
      out.add(
          new Guidance(
              text(g.path("id")),
              text(g.path("kind")),
              text(g.path("title")),
              text(g.path("description")),
              text(g.path("phone")),
              text(g.path("url")),
              cite(evidence, g.path("evidenceIds"))));
    }
    return out;
  }

  /** 단지·건물. 위치 전체를 보류했으면 빼고, 이름·주소·지역 코드 중 보류한 칸만 비워요. */
  static List<Site> sites(JsonNode detail) {
    List<Site> out = new ArrayList<>();
    JsonNode all = detail.path("locations");
    for (int i = 0; i < all.size(); i++) {
      String at = "/locations/" + i;
      if (heldWhole(detail, at)) {
        continue;
      }
      JsonNode l = all.get(i);
      String name = held(detail, at + "/complexName") ? null : text(l.path("complexName"));
      if (name == null && !held(detail, at + "/buildingName")) {
        name = text(l.path("buildingName"));
      }
      String code = held(detail, at + "/regionCode") ? null : text(l.path("regionCode"));
      out.add(
          new Site(
              text(l.path("id")),
              text(l.path("kind")),
              name,
              held(detail, at + "/address") ? null : text(l.path("address")),
              code == null || code.length() < 5 ? code : code.substring(0, 5),
              null,
              null,
              null,
              List.of()));
    }
    return out;
  }

  /**
   * 공급 묶음별 주택형 줄. 묶음 하나(단지·주택형·공급대상)가 한 줄이고, 그 묶음의 가격이 대상별로 나뉘면(가군·나군, 주거급여수급자 등) 가격 대상마다 한 줄이에요.
   * 다른 묶음끼리는 주택형 이름이 같아도 합치지 않아요(2026-10-26 원문 대조: 이름만으로 합쳐 다른 단지 임대료가 붙고 호수가 더해졌음).
   *
   * <ul>
   *   <li>공급 호수: 묶음 전체 수량(대상 없는 OFFERED)이 있으면 그것만, 없으면 대상별 수량의 합. 하위 수량(부모가 있거나 COMPONENT)은 세지 않아요.
   *       가격 대상이 여럿이라 줄이 여럿이면 첫 줄에만 적어 합이 두 번 세지지 않게 해요(같은 묶음은 supplyGroupId가 같아요).
   *   <li>가격만 있고 수량이 없는 묶음(분양가표처럼 다른 표에서 온 묶음)은 같은 단지·같은 주택형 표기(코드 뒤 이름, 예: 59A)의 수량 묶음이 하나뿐일 때 그
   *       묶음의 가격으로 붙여요. 여럿이거나 없으면 따로 한 줄이에요.
   *   <li>분양가는 그 줄의 분양가(SALE_PRICE) 가장 낮은 값·높은 값이에요(층·안별로 여러 개).
   * </ul>
   *
   * <p>보류 범위에 따라 가려요:
   *
   * <ul>
   *   <li>공급 묶음 전체(/supplyGroups/{i}이나 그 위)나 수량·가격 밖의 칸(면적·주택형 등)을 보류한 묶음은 빼요.
   *   <li>수량만 보류(/supplyGroups/{i}/counts나 그 안)했으면 그 묶음의 공급 호수만 null이에요.
   *   <li>가격만 보류(/supplyGroups/{i}/prices나 가격 항목 하나)했으면 그 가격 종류만 null이고 근거도 빼요. 가격 항목의 종류를 모르면(항목
   *       전체나 종류 칸 보류) 그 가격 대상의 가격이 모두 null이에요.
   * </ul>
   */
  public static List<UnitType> unitTypes(JsonNode detail) {
    Map<String, Evidence> evidence = evidence(detail);
    Map<String, String> siteNames = siteNames(detail);
    JsonNode groups = detail.path("supplyGroups");
    // 가격만 있는 묶음을 붙일 수량 묶음: (단지, 주택형 표기) → 묶음 번호들
    Map<String, List<Integer>> countedByLabel = new LinkedHashMap<>();
    for (int i = 0; i < groups.size(); i++) {
      JsonNode g = groups.get(i);
      if (text(g.path("housingTypeCode")) != null
          && !groupHeld(detail, "/supplyGroups/" + i)
          && hasOffered(g.path("counts"))) {
        countedByLabel.computeIfAbsent(labelKey(g), k -> new ArrayList<>()).add(i);
      }
    }
    Map<Integer, Map<String, PriceTier>> tiersOf = new LinkedHashMap<>();
    for (int i = 0; i < groups.size(); i++) {
      JsonNode g = groups.get(i);
      String at = "/supplyGroups/" + i;
      if (text(g.path("housingTypeCode")) == null || groupHeld(detail, at)) {
        continue;
      }
      int owner = i;
      if (!hasOffered(g.path("counts")) && g.path("prices").size() > 0) {
        List<Integer> same = countedByLabel.getOrDefault(labelKey(g), List.of());
        if (same.size() == 1) {
          owner = same.getFirst();
        }
      }
      Map<String, PriceTier> tiers = tiersOf.computeIfAbsent(owner, k -> new LinkedHashMap<>());
      collectPrices(detail, at, g, tiers);
    }
    Map<Integer, Integer> countOf = new HashMap<>();
    for (int i : tiersOf.keySet()) {
      JsonNode g = groups.get(i);
      if (!held(detail, "/supplyGroups/" + i + "/counts")) {
        Integer count = offered(g.path("counts"));
        if (count == null && "HOUSING_UNIT".equals(text(g.path("itemKind")))) {
          count = 1; // 호 하나가 공급 묶음 하나
        }
        countOf.put(i, count);
      }
    }
    dropMergedCellCopies(detail, countOf);
    List<UnitType> out = new ArrayList<>();
    for (Map.Entry<Integer, Map<String, PriceTier>> entry : tiersOf.entrySet()) {
      int i = entry.getKey();
      JsonNode g = groups.get(i);
      Integer count = countOf.get(i);
      List<PriceTier> tiers = new ArrayList<>(entry.getValue().values());
      if (tiers.isEmpty()) {
        tiers.add(new PriceTier(List.of()));
      }
      List<String> groupTargets = strings(g.path("scope").path("targetGroups"));
      boolean first = true;
      for (PriceTier t : tiers) {
        out.add(
            new UnitType(
                text(g.path("housingTypeCode")),
                t.targets.isEmpty() ? groupTargets : t.targets,
                decimal(g.path("exclusiveAreaSqm")),
                t.depositHeld ? null : amount(t.deposit),
                t.rentHeld ? null : amount(t.rent),
                first ? count : null,
                priceEvidence(
                    evidence, t.depositHeld ? null : t.deposit, t.rentHeld ? null : t.rent),
                text(g.path("id")),
                siteNames.get(text(g.path("locationId"))),
                t.saleHeld ? null : t.saleMin,
                t.saleHeld ? null : t.saleMax));
        first = false;
      }
    }
    return out;
  }

  /**
   * 병합 칸 복사 의심: 묶음 호수의 합이 공고에 적힌 모집 호수보다 크면, 같은 단지·같은 주택형 코드(첫 낱말, 예: 055.0000A)에 같은 호수가 적힌 묶음들은 표의
   * 병합 칸 하나가 여러 줄에 복사된 것일 수 있어 그 호수를 모두 비워요(어느 줄의 값인지 몰라서, 틀린 값보다 「공고 확인」). 2026-10-26 원문 대조: 「55A
   * 155」 병합 칸이 55A·55AH 두 줄에 들어가 합이 공고 모집 호수 175보다 커졌음.
   */
  private static void dropMergedCellCopies(JsonNode detail, Map<Integer, Integer> countOf) {
    Integer noticeTotal =
        held(detail, "/notice/counts") ? null : offered(detail.path("notice").path("counts"));
    int sum = countOf.values().stream().mapToInt(c -> c == null ? 0 : c).sum();
    if (noticeTotal == null || sum <= noticeTotal) {
      return;
    }
    JsonNode groups = detail.path("supplyGroups");
    Map<String, List<Integer>> family = new HashMap<>();
    countOf.forEach(
        (i, count) -> {
          if (count != null) {
            JsonNode g = groups.get(i);
            String code = text(g.path("housingTypeCode")).trim().split("\\s+")[0];
            family
                .computeIfAbsent(
                    text(g.path("locationId")) + "|" + code + "|" + count, k -> new ArrayList<>())
                .add(i);
          }
        });
    family.values().stream()
        .filter(same -> same.size() > 1)
        .flatMap(List::stream)
        .forEach(i -> countOf.put(i, null));
  }

  /** 한 가격 대상(가격 항목의 대상 계층이 같은 것)의 보여 줄 가격. */
  private static final class PriceTier {
    final List<String> targets;
    JsonNode deposit;
    JsonNode rent;
    Long saleMin;
    Long saleMax;
    boolean depositHeld;
    boolean rentHeld;
    boolean saleHeld;

    PriceTier(List<String> targets) {
      this.targets = targets;
    }
  }

  /**
   * 묶음의 가격 항목을 가격 대상별로 모아요. 종류마다 첫 금액을 쓰고, 그 앞이나 그 자리에 그 종류(또는 종류를 모르는)의 보류 항목이 있으면 그 종류는 보여 주지
   * 않아요(뒤의 다른 항목으로 대신하지 않아요, 다른 조건의 금액일 수 있어요). 분양가는 보류가 없을 때 가장 낮은·높은 값이에요.
   */
  private static void collectPrices(
      JsonNode detail, String at, JsonNode group, Map<String, PriceTier> tiers) {
    JsonNode prices = group.path("prices");
    boolean wholeHeld = heldWhole(detail, at + "/prices");
    for (int j = 0; j < prices.size(); j++) {
      JsonNode p = prices.get(j);
      List<String> targets = strings(p.path("scope").path("targetGroups"));
      PriceTier t = tiers.computeIfAbsent(String.join("|", targets), k -> new PriceTier(targets));
      String item = at + "/prices/" + j;
      String kind = text(p.path("kind"));
      if (wholeHeld || held(detail, item)) {
        boolean kindUnknown = wholeHeld || heldWhole(detail, item) || held(detail, item + "/kind");
        if ((kindUnknown || "DEPOSIT".equals(kind)) && t.deposit == null) {
          t.depositHeld = true;
        }
        if ((kindUnknown || "MONTHLY_RENT".equals(kind)) && t.rent == null) {
          t.rentHeld = true;
        }
        if (kindUnknown || "SALE_PRICE".equals(kind)) {
          t.saleHeld = true;
        }
        continue;
      }
      if (!p.path("amountKrw").isNumber()) {
        continue;
      }
      long won = p.path("amountKrw").asLong();
      if ("DEPOSIT".equals(kind) && t.deposit == null && !t.depositHeld) {
        t.deposit = p;
      } else if ("MONTHLY_RENT".equals(kind) && t.rent == null && !t.rentHeld) {
        t.rent = p;
      } else if ("SALE_PRICE".equals(kind)) {
        t.saleMin = t.saleMin == null ? won : Math.min(t.saleMin, won);
        t.saleMax = t.saleMax == null ? won : Math.max(t.saleMax, won);
      }
    }
  }

  private static boolean hasOffered(JsonNode counts) {
    for (JsonNode c : counts) {
      if ("OFFERED".equals(text(c.path("kind")))) {
        return true;
      }
    }
    return false;
  }

  /** 가격만 있는 묶음을 수량 묶음에 붙일 때 쓰는 열쇠: 단지 + 주택형 표기의 마지막 낱말(「059.9000A 59A」와 「059.0000A 59A」는 59A). */
  private static String labelKey(JsonNode group) {
    String code = text(group.path("housingTypeCode"));
    String[] words = code == null ? new String[] {""} : code.trim().split("\\s+");
    return text(group.path("locationId")) + "|" + words[words.length - 1];
  }

  /** 단지 ID → 이름(단지명, 없으면 건물명). 보류한 이름은 빼요. */
  private static Map<String, String> siteNames(JsonNode detail) {
    Map<String, String> out = new HashMap<>();
    JsonNode all = detail.path("locations");
    for (int i = 0; i < all.size(); i++) {
      String at = "/locations/" + i;
      JsonNode l = all.get(i);
      if (heldWhole(detail, at) || text(l.path("id")) == null) {
        continue;
      }
      String name = held(detail, at + "/complexName") ? null : text(l.path("complexName"));
      if (name == null && !held(detail, at + "/buildingName")) {
        name = text(l.path("buildingName"));
      }
      if (name != null) {
        out.put(text(l.path("id")), name);
      }
    }
    return out;
  }

  /**
   * 자격 조건. 상세에서 보류한 조건(/eligibility/{i}, 같은 순서)은 확인 필요로 표시하고 근거를 비워요. 근거는 같은 ID의 상세 자격 조건에서 찾아요.
   */
  static List<Condition> conditions(JsonNode payload, JsonNode detail) {
    Map<String, Evidence> evidence = evidence(detail);
    List<Condition> out = new ArrayList<>();
    JsonNode all = payload.path("conditions");
    for (int i = 0; i < all.size(); i++) {
      JsonNode c = all.get(i);
      boolean held = held(detail, "/eligibility/" + i);
      JsonNode source = held ? null : eligibility(detail, text(c.path("id")), i);
      out.add(
          new Condition(
              text(c.path("id")),
              text(c.path("category")),
              text(c.path("target")),
              strings(c.path("targetGroups")),
              text(c.path("description")),
              text(c.path("originalText")),
              c.path("inReview").asBoolean(false) || held,
              source == null ? List.of() : cite(evidence, source.path("evidenceIds"))));
    }
    return out;
  }

  static List<FileLink> files(JsonNode detail) {
    List<FileLink> out = new ArrayList<>();
    JsonNode all = detail.path("documents");
    for (int i = 0; i < all.size(); i++) {
      if (held(detail, "/documents/" + i)) {
        continue;
      }
      JsonNode d = all.get(i);
      String url = text(d.path("originalUrl"));
      if (url != null) {
        out.add(new FileLink(text(d.path("name")), url));
      }
    }
    return out;
  }

  /**
   * 호 단위(HOUSING_UNIT) 공급 묶음. siteId가 있으면 그 단지·건물 것만. 주소는 단지·건물 주소예요. 보류한 호(묶음 전체나 수량·가격 밖의 칸)는 빼고,
   * 가격만 보류한 호는 그 보증금·월임대료만 비우고(근거도 빼요) 보여 줘요. 보류한 위치의 주소는 비워요.
   */
  public static List<NoticeUnitResponse> units(JsonNode detail, String siteId) {
    Map<String, Evidence> evidence = evidence(detail);
    Map<String, String> siteNames = siteNames(detail);
    Map<String, String> addresses = new LinkedHashMap<>();
    JsonNode locations = detail.path("locations");
    for (int i = 0; i < locations.size(); i++) {
      String at = "/locations/" + i;
      boolean hidden = heldWhole(detail, at) || held(detail, at + "/address");
      addresses.put(
          text(locations.get(i).path("id")),
          hidden ? null : text(locations.get(i).path("address")));
    }
    List<NoticeUnitResponse> out = new ArrayList<>();
    JsonNode groups = detail.path("supplyGroups");
    for (int i = 0; i < groups.size(); i++) {
      JsonNode g = groups.get(i);
      String at = "/supplyGroups/" + i;
      if (groupHeld(detail, at)) {
        continue;
      }
      String location = text(g.path("locationId"));
      if (!"HOUSING_UNIT".equals(text(g.path("itemKind")))
          || (siteId != null && !siteId.equals(location))) {
        continue;
      }
      Map<String, PriceTier> tiers = new LinkedHashMap<>();
      collectPrices(detail, at, g, tiers);
      List<NoticeUnitResponse.Price> prices = new ArrayList<>();
      for (PriceTier t : tiers.values()) {
        prices.add(
            new NoticeUnitResponse.Price(
                t.targets,
                t.depositHeld ? null : amount(t.deposit),
                t.rentHeld ? null : amount(t.rent)));
      }
      // depositWon·rentWon은 첫 가격 대상 (예전 응답과 같아요)
      PriceTier t = tiers.isEmpty() ? new PriceTier(List.of()) : tiers.values().iterator().next();
      JsonNode deposit = t.depositHeld ? null : t.deposit;
      JsonNode rent = t.rentHeld ? null : t.rent;
      out.add(
          new NoticeUnitResponse(
              text(g.path("id")),
              location,
              siteNames.get(location),
              addresses.get(location),
              text(g.path("unitLabel")),
              text(g.path("floor")),
              text(g.path("housingTypeCode")),
              decimal(g.path("exclusiveAreaSqm")),
              amount(deposit),
              amount(rent),
              prices,
              priceEvidence(evidence, deposit, rent)));
    }
    // 단지별로 이어서 보이게 위치 순서로 (같은 단지 안은 원문 순서)
    List<String> order = new ArrayList<>(addresses.keySet());
    out.sort(
        Comparator.comparingInt(
            u ->
                u.siteId() == null || !order.contains(u.siteId())
                    ? order.size()
                    : order.indexOf(u.siteId())));
    return out;
  }

  public static boolean hasUnits(JsonNode detail) {
    for (JsonNode g : detail.path("supplyGroups")) {
      if ("HOUSING_UNIT".equals(text(g.path("itemKind")))) {
        return true;
      }
    }
    return false;
  }

  /** 원문 확인 전까지 보여 주지 않는 항목. */
  static List<HeldItem> heldItems(JsonNode detail) {
    List<HeldItem> out = new ArrayList<>();
    for (JsonNode h : detail.path("quality").path("heldItems")) {
      String target = text(h.path("target"));
      String section = target == null ? null : target.split("/", 3)[target.startsWith("/") ? 1 : 0];
      out.add(new HeldItem(section, target, text(h.path("description"))));
    }
    return out;
  }

  /** 이 위치(pointer)가 보류 범위와 겹치는지: 그 항목 자체, 그 위 섹션, 그 안의 칸 중 하나라도 보류됨. */
  private static boolean held(JsonNode detail, String pointer) {
    return NoticeContent.held(detail.path("quality").path("heldItems"), pointer);
  }

  /** 이 위치 전체가 보류됐는지: 그 항목 자체나 그 위 섹션이 보류됨 (안의 칸 하나만 보류한 경우는 아님). */
  private static boolean heldWhole(JsonNode detail, String pointer) {
    for (JsonNode h : detail.path("quality").path("heldItems")) {
      String target = h.path("target").asString("");
      if (!target.isEmpty() && (pointer.equals(target) || pointer.startsWith(target + "/"))) {
        return true;
      }
    }
    return false;
  }

  /**
   * 공급(OFFERED) 수량. 전체 수량(대상 없는 줄)이 있으면 그 합만, 없으면 대상별 수량의 합이에요. 하위 수량(부모가 있거나 COMPONENT)은 세지 않아요.
   * (2026-10-26 원문 대조: 「묶음 전체 34」와 「대상별 21·1·1…(합 34)」을 다 더해 68로 보였음)
   *
   * <p>대상별 합에서는 대상 이름이 소계(「특별공급 계」·「합계」·「소계」)인 줄을 빼요: 표의 소계 줄이 대상처럼 들어오면 두 번 세져요(검암역 60A 25호가 46호로
   * 보였음). 같은 묶음에 대상 없는 총 세대수(TOTAL_HOUSING)가 있는데 대상별 합이 그보다 크면 어딘가 겹친 값이라 null이에요.
   */
  private static Integer offered(JsonNode counts) {
    Integer whole = null;
    Integer byTarget = null;
    Integer housing = null;
    for (JsonNode c : counts) {
      if (!c.path("value").isNumber()
          || text(c.path("parentCountId")) != null
          || "COMPONENT".equals(text(c.path("aggregationRole")))) {
        continue;
      }
      int value = c.path("value").asInt();
      List<String> targets = strings(c.path("scope").path("targetGroups"));
      if ("TOTAL_HOUSING".equals(text(c.path("kind"))) && targets.isEmpty()) {
        housing = (housing == null ? 0 : housing) + value;
      }
      if (!"OFFERED".equals(text(c.path("kind")))) {
        continue;
      }
      if (targets.isEmpty()) {
        whole = (whole == null ? 0 : whole) + value;
      } else if (targets.stream().noneMatch(t -> SUBTOTAL.matcher(t.trim()).find())) {
        byTarget = (byTarget == null ? 0 : byTarget) + value;
      }
    }
    if (whole != null) {
      return whole;
    }
    return byTarget != null && housing != null && byTarget > housing ? null : byTarget;
  }

  /** 표의 소계 줄 이름: 「특별공급 계」, 「특별공급계」, 「합계」, 「소계」, 「총계」, 「계」. */
  private static final Pattern SUBTOTAL = Pattern.compile("(?:^|\\s|공급)(?:소|합|총)?계$");

  /**
   * 공급 묶음을 통째로 빼야 하는지: 묶음 자체나 그 위 섹션을 보류했거나, 수량(counts)·가격(prices) 밖의 칸(주택형·면적 등)을 보류함. 수량·가격만
   * 보류했으면 그 값만 가리고 묶음은 보여 줘요.
   */
  private static boolean groupHeld(JsonNode detail, String at) {
    if (heldWhole(detail, at)) {
      return true;
    }
    for (JsonNode h : detail.path("quality").path("heldItems")) {
      String target = h.path("target").asString("");
      if (target.startsWith(at + "/")
          && !inside(target, at + "/counts")
          && !inside(target, at + "/prices")) {
        return true;
      }
    }
    return false;
  }

  private static boolean inside(String target, String pointer) {
    return target.equals(pointer) || target.startsWith(pointer + "/");
  }

  /** 공급 수량을 모르는 묶음이 있는지: 묶음을 통째로 빼거나 수량을 보류한 묶음. 이때 주택형별 합을 공고 모집 수로 쓰지 않아요. */
  private static boolean supplyCountsHeld(JsonNode detail) {
    if (heldWhole(detail, "/supplyGroups")) {
      return true;
    }
    JsonNode groups = detail.path("supplyGroups");
    for (int i = 0; i < groups.size(); i++) {
      String at = "/supplyGroups/" + i;
      if (groupHeld(detail, at) || held(detail, at + "/counts")) {
        return true;
      }
    }
    return false;
  }

  private static Long amount(JsonNode price) {
    return price == null ? null : price.path("amountKrw").asLong();
  }

  /** 보여 주는 보증금·월임대료의 근거 (같은 근거는 한 번만). */
  private static List<Evidence> priceEvidence(
      Map<String, Evidence> evidence, JsonNode deposit, JsonNode rent) {
    Set<String> ids = new LinkedHashSet<>();
    for (JsonNode p : new JsonNode[] {deposit, rent}) {
      if (p != null) {
        p.path("evidenceIds").forEach(id -> ids.add(id.asString()));
      }
    }
    return ids.stream().map(evidence::get).filter(Objects::nonNull).toList();
  }

  /** 같은 ID의 상세 자격 조건 (보통 같은 순서고, 순서가 다르면 ID로 찾아요). 없으면 null. */
  private static JsonNode eligibility(JsonNode detail, String id, int index) {
    JsonNode all = detail.path("eligibility");
    JsonNode same = all.path(index);
    if (!same.isMissingNode() && (id == null || id.equals(text(same.path("id"))))) {
      return same;
    }
    for (JsonNode e : all) {
      if (id != null && id.equals(text(e.path("id")))) {
        return e;
      }
    }
    return null;
  }

  /** 상세의 근거 ID → 화면에 보여 줄 근거. 문서 이름은 sourceId로 documents에서 찾아요. */
  private static Map<String, Evidence> evidence(JsonNode detail) {
    Map<String, String> names = new LinkedHashMap<>();
    for (JsonNode d : detail.path("documents")) {
      names.put(text(d.path("id")), text(d.path("name")));
    }
    Map<String, Evidence> out = new LinkedHashMap<>();
    for (JsonNode e : detail.path("evidence")) {
      JsonNode locator = e.path("locator");
      // 쪽은 PDF 쪽 근거와, 쪽 표시가 있는 PDF 글자의 글자 범위 근거(추출이 page를 실은 경우)에서 읽어요. 표 행 근거는 쪽이 없어요
      String kind = text(locator.path("kind"));
      boolean paged = "PDF_PAGE".equals(kind) || "TEXT_RANGE".equals(kind);
      out.put(
          text(e.path("id")),
          new Evidence(
              text(e.path("quote")),
              paged && locator.path("page").isNumber() ? locator.path("page").asInt() : null,
              paged ? text(locator.path("printedPage")) : null,
              names.get(text(e.path("sourceId")))));
    }
    return out;
  }

  /** evidenceIds 순서대로 근거를 찾아요. 없는 ID는 건너뛰어요. */
  private static List<Evidence> cite(Map<String, Evidence> evidence, JsonNode ids) {
    List<Evidence> out = new ArrayList<>();
    for (JsonNode id : ids) {
      Evidence e = evidence.get(id.asString());
      if (e != null) {
        out.add(e);
      }
    }
    return out;
  }

  private static boolean within(LocalDate today, String starts, String ends) {
    LocalDate from = day(starts);
    LocalDate to = day(ends);
    if (from == null && to == null) {
      return false;
    }
    return (from == null || !today.isBefore(from)) && (to == null || !today.isAfter(to));
  }

  /** "2026-10-01" 또는 "2026-10-01T10:00:00+09:00"의 날짜. */
  private static LocalDate day(String value) {
    return value == null || value.length() < 10 ? null : LocalDate.parse(value.substring(0, 10));
  }

  static String text(JsonNode node) {
    return node == null || node.isMissingNode() || node.isNull() ? null : node.asString();
  }

  static BigDecimal decimal(JsonNode node) {
    return node.isNumber() ? node.decimalValue() : null;
  }

  static List<String> strings(JsonNode array) {
    List<String> out = new ArrayList<>();
    for (JsonNode v : array) {
      out.add(v.asString());
    }
    return out;
  }
}
