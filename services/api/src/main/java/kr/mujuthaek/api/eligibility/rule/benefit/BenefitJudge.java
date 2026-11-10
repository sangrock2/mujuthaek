package kr.mujuthaek.api.eligibility.rule.benefit;

import static kr.mujuthaek.api.eligibility.rule.Status.MET;
import static kr.mujuthaek.api.eligibility.rule.Status.NOT_MET;
import static kr.mujuthaek.api.eligibility.rule.Status.UNKNOWN;

import java.time.LocalDate;
import java.time.YearMonth;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import kr.mujuthaek.api.common.region.CityDistricts;
import kr.mujuthaek.api.eligibility.rule.Applicant;
import kr.mujuthaek.api.eligibility.rule.Bands;
import kr.mujuthaek.api.eligibility.rule.IncomeBenchmarks;
import kr.mujuthaek.api.eligibility.rule.Item;
import kr.mujuthaek.api.eligibility.rule.Overall;
import kr.mujuthaek.api.eligibility.rule.Status;

/**
 * 혜택 자격 판정 (contracts/schemas/benefit-condition-types.draft.md). 조건 한 줄마다 충족·불충족·확인 필요를 정하고, 같은 그룹은
 * "또는", 다른 그룹은 "그리고"로 묶어요. 입력은 공고와 같은 구간 값이에요.
 *
 * <ul>
 *   <li>값으로 못 바꾼 조건(known=false)과 입력 칸이 없는 조건(취업 상태·임차 조건 등)은 확인 필요
 *   <li>거주 조건은 사는 곳이 그 지역이면 충족, 아니면 이사하면 받을 수 있어서 확인 필요 (지원 불가로 떨어뜨리지 않아요)
 *   <li>중복 수혜(EXCLUSIVE)·선정 우선순위(PRIORITY)는 판정하지 않고 안내로만 줘요
 *   <li>사람 확인 전 정책은 지원 가능을 넘지 않아요 (확인 필요)
 * </ul>
 */
public final class BenefitJudge {

  private BenefitJudge() {}

  /**
   * 조건 한 줄.
   *
   * @param value type마다 정해진 값을 읽은 것 (known=false면 빈 맵)
   */
  public record Condition(
      String type, Map<String, Object> value, int group, boolean known, String rawText) {}

  /** 그룹 하나: 안의 조건 중 하나라도 충족이면 충족. */
  public record Group(int group, Status status, List<Item> items) {}

  /** 조건 수 요약 (그룹 단위). */
  public record Summary(int total, int met, int notMet, int unknown) {}

  /**
   * @param groups 판정한 그룹 (원문 순서)
   * @param notes 판정하지 않고 안내로만 보여 주는 조건 원문 (중복 수혜 불가, 선정 우선순위)
   * @param reason 사람 확인 전이라 확인 필요로 둔 경우 그 이유, 아니면 null
   */
  public record Result(
      Overall overall, Summary summary, List<Group> groups, List<String> notes, String reason) {}

  private static final Set<String> NOTES = Set.of("EXCLUSIVE", "PRIORITY");
  private static final String MEDIAN = "MEDIAN_INCOME";

  public static Result judge(
      List<Condition> conditions,
      boolean needsReview,
      Applicant a,
      LocalDate today,
      IncomeBenchmarks benchmarks) {
    Map<Integer, List<Item>> byGroup = new LinkedHashMap<>();
    List<String> notes = new ArrayList<>();
    for (Condition c : conditions) {
      if (NOTES.contains(c.type())) {
        notes.add(c.rawText());
        continue;
      }
      byGroup
          .computeIfAbsent(c.group(), g -> new ArrayList<>())
          .add(judge(c, a, today, benchmarks));
    }
    List<Group> groups = new ArrayList<>();
    byGroup.forEach(
        (g, items) ->
            groups.add(new Group(g, Status.any(items.stream().map(Item::status).toList()), items)));
    Overall overall = Overall.of(Status.all(groups.stream().map(Group::status).toList()));
    String reason = null;
    if (needsReview && overall == Overall.ELIGIBLE) {
      overall = Overall.NEEDS_INPUT;
      reason = "정책 내용을 확인하는 중이에요. 원문 조건을 확인해 주세요";
    }
    return new Result(overall, summary(groups), groups, notes, reason);
  }

  private static Summary summary(List<Group> groups) {
    int met = 0;
    int notMet = 0;
    int unknown = 0;
    for (Group g : groups) {
      switch (g.status()) {
        case MET -> met++;
        case NOT_MET -> notMet++;
        case UNKNOWN -> unknown++;
      }
    }
    return new Summary(groups.size(), met, notMet, unknown);
  }

  /** 조건 한 줄. 화면 문구(label)는 조건 원문이에요. */
  static Item judge(Condition c, Applicant a, LocalDate today, IncomeBenchmarks benchmarks) {
    if (!c.known()) return unknown(c, "원문 조건을 확인해 주세요");
    return switch (c.type()) {
      case "AGE" -> age(c, a, today);
      case "MARITAL" -> marital(c, a, today);
      case "NEWLYWED_YEARS" -> newlywed(c, a, today, integer(c, "max"));
      case "CHILDREN" -> children(c, a);
      case "HOUSEHOLD_TYPE" -> householdType(c, a);
      case "WELFARE_STATUS" -> welfare(c, a);
      case "INCOME_MEDIAN_PCT" -> incomePercent(c, a, today, benchmarks);
      case "INCOME_AMOUNT" -> incomeAmount(c, a, today, benchmarks);
      case "ASSET_AMOUNT" -> asset(c, a);
      case "RESIDENCE" -> residence(c, a);
      case "MOVE_IN" -> unknown(c, "전입하면 받을 수 있어요");
      case "HOMELESS" -> homeless(c, a, null);
      case "HOMELESS_YEARS" -> homeless(c, a, integer(c, "min"));
      case "FIRST_HOME" ->
          Boolean.TRUE.equals(a.homeOwner())
              ? item(c, NOT_MET, "집이 있으면 받을 수 없어요", List.of())
              : unknown(c, "예전에 집을 가진 적이 있는지 확인해 주세요");
      default -> unknown(c, "이 조건은 직접 확인해 주세요");
    };
  }

  private static Item age(Condition c, Applicant a, LocalDate today) {
    int[] ages = a.ages(today);
    if (ages == null) return need(c, "생년월일을 넣으면 판정돼요", "applicant.birthDate");
    Status s = Bands.ageWithin(ages, integer(c, "min"), integer(c, "max"));
    return item(c, s, reason(s, "나이가 맞지 않아요"), List.of());
  }

  private static Item marital(Condition c, Applicant a, LocalDate today) {
    if (a.marital() == null) return need(c, "혼인 상태를 넣으면 판정돼요", "applicant.marital");
    List<String> allowed = strings(c, "in");
    if (allowed.contains(a.marital())) return item(c, MET, null, List.of());
    if (allowed.contains("NEWLYWED") && "MARRIED".equals(a.marital())) {
      return newlywed(c, a, today, 7); // 신혼 기간은 흔히 7년 (정책마다 다르면 NEWLYWED_YEARS 줄이 따로 와요)
    }
    return item(c, NOT_MET, "혼인 상태가 맞지 않아요", List.of());
  }

  private static Item newlywed(Condition c, Applicant a, LocalDate today, Integer maxYears) {
    if (a.marital() == null) return need(c, "혼인 상태를 넣으면 판정돼요", "applicant.marital");
    if ("ENGAGED".equals(a.marital())) return unknown(c, "예비 신혼부부도 받을 수 있는지 확인해 주세요");
    if (!"MARRIED".equals(a.marital())) return item(c, NOT_MET, "혼인 기간 조건이 있어요", List.of());
    if (maxYears == null) return item(c, MET, null, List.of());
    YearMonth married = a.marriedOn();
    if (married == null) return need(c, "혼인 신고 연월을 넣으면 판정돼요", "applicant.marriedOn");
    // 혼인 연월만 알아서 달 단위로 봐요: 그 달 1일과 말일 모두 기간 안이면 충족
    long newest = ChronoUnit.YEARS.between(married.atEndOfMonth(), today);
    long oldest = ChronoUnit.YEARS.between(married.atDay(1), today);
    Status s = oldest < maxYears ? MET : newest >= maxYears ? NOT_MET : UNKNOWN;
    return item(c, s, s == UNKNOWN ? Bands.BOUNDARY : reason(s, "혼인 기간이 지났어요"), List.of());
  }

  private static Item children(Condition c, Applicant a) {
    if (a.children() == null) return need(c, "자녀 수를 넣으면 판정돼요", "applicant.children");
    Integer min = integer(c, "minCount");
    if (min != null && a.children() < min) return item(c, NOT_MET, "자녀 수가 모자라요", List.of());
    if (min == null && a.children() == 0) return item(c, NOT_MET, "자녀가 있어야 해요", List.of());
    if (integer(c, "maxAgeOfYoungest") != null) return unknown(c, "막내 나이를 확인해 주세요");
    return item(c, MET, null, List.of());
  }

  private static Item householdType(Condition c, Applicant a) {
    List<Status> results = new ArrayList<>();
    for (String type : strings(c, "in")) {
      results.add(
          switch (type) {
            case "SINGLE_PERSON" ->
                a.householdSize() == null ? UNKNOWN : a.householdSize() == 1 ? MET : NOT_MET;
            case "SINGLE_PARENT" ->
                a.welfareStatuses() == null
                    ? UNKNOWN
                    : a.welfareStatuses().contains("SINGLE_PARENT") ? MET : NOT_MET;
            case "MULTI_CHILD" ->
                a.children() == null ? UNKNOWN : a.children() >= 2 ? MET : UNKNOWN;
            default -> UNKNOWN;
          });
    }
    Status s = Status.any(results);
    return item(c, s, s == UNKNOWN ? "가구 유형을 확인해 주세요" : reason(s, "가구 유형이 맞지 않아요"), List.of());
  }

  private static Item welfare(Condition c, Applicant a) {
    if (a.welfareStatuses() == null) {
      return need(c, "수급 여부를 넣으면 판정돼요", "applicant.welfareStatuses");
    }
    boolean any = strings(c, "in").stream().anyMatch(a.welfareStatuses()::contains);
    return item(c, any ? MET : NOT_MET, any ? null : "해당하는 수급 자격이 없어요", List.of());
  }

  /** 기준중위소득 비율. 가구 소득은 받은 % 구간 그대로, 본인 소득은 1인 가구 기준으로 바꿔 비교해요. */
  private static Item incomePercent(
      Condition c, Applicant a, LocalDate today, IncomeBenchmarks benchmarks) {
    Integer max = integer(c, "max");
    if (max == null) return unknown(c, "원문 조건을 확인해 주세요");
    boolean personal = "PERSONAL".equals(text(c, "basis"));
    Map<String, Bands.Range> bands = personal ? a.personalIncome() : a.householdIncomeOrSelf();
    Bands.Range pct = bands == null ? null : bands.get(MEDIAN);
    if (pct == null && !personal) {
      Bands.Range own = median(a.personalIncome());
      if (own != null) return ownIncomeOnly(c, own.atMost(max));
    }
    if (pct == null) return need(c, Bands.NO_INCOME, "applicant.income");
    if (!personal || Integer.valueOf(1).equals(a.householdSize())) {
      return income(c, pct.atMost(max));
    }
    if (a.householdSize() == null) {
      return need(c, "세대원 수를 넣으면 판정돼요", "applicant.householdSize");
    }
    int year = yearOf(a, today);
    Long base = benchmarks.monthlyWon(MEDIAN, year, a.householdSize());
    Long single = benchmarks.monthlyWon(MEDIAN, year, 1);
    if (base == null || single == null) return unknown(c, "그해 기준 금액을 아직 준비하지 못했어요");
    return income(c, pct.times(base / 100.0).atMost(single * max / 100.0));
  }

  /** 연 소득 금액 (만 원). 받은 % 구간을 기준 월액으로 바꿔 연 금액 구간으로 비교해요. */
  private static Item incomeAmount(
      Condition c, Applicant a, LocalDate today, IncomeBenchmarks benchmarks) {
    Integer max = integer(c, "max");
    if (max == null) return unknown(c, "원문 조건을 확인해 주세요");
    boolean household = "HOUSEHOLD".equals(text(c, "basis"));
    Map<String, Bands.Range> bands = household ? a.householdIncomeOrSelf() : a.personalIncome();
    Bands.Range pct = bands == null ? null : bands.get(MEDIAN);
    boolean ownOnly = false;
    if (pct == null && household) {
      pct = median(a.personalIncome());
      ownOnly = pct != null;
    }
    if (pct == null) return need(c, Bands.NO_INCOME, "applicant.income");
    if (a.householdSize() == null) {
      return need(c, "세대원 수를 넣으면 판정돼요", "applicant.householdSize");
    }
    Long base = benchmarks.monthlyWon(MEDIAN, yearOf(a, today), a.householdSize());
    if (base == null) return unknown(c, "그해 기준 금액을 아직 준비하지 못했어요");
    Status status = pct.times(base * 12 / 100.0).atMost(max * 10_000.0);
    return ownOnly ? ownIncomeOnly(c, status) : income(c, status);
  }

  private static Item income(Condition c, Status s) {
    return item(c, s, s == UNKNOWN ? Bands.BOUNDARY : reason(s, "소득이 기준을 넘어요"), List.of());
  }

  /**
   * 가구 소득 기준인데 본인 소득만 받았을 때 (2인 이상 가구). 가구 소득은 본인 소득보다 작을 수 없어서 본인 소득만으로 넘으면 불충족, 아니면 원문을 보게 해요.
   */
  private static Item ownIncomeOnly(Condition c, Status own) {
    return own == NOT_MET
        ? item(c, NOT_MET, Bands.OWN_INCOME_OVER, List.of())
        : unknown(c, Bands.HOUSEHOLD_INCOME_UNKNOWN);
  }

  private static Bands.Range median(Map<String, Bands.Range> bands) {
    return bands == null ? null : bands.get(MEDIAN);
  }

  private static Item asset(Condition c, Applicant a) {
    Integer max = integer(c, "max");
    if (max == null) return unknown(c, "원문 조건을 확인해 주세요");
    String kind = text(c, "kind");
    Bands.Range range;
    String need;
    if (kind == null || "TOTAL".equals(kind)) {
      range = a.assets();
      need = "applicant.assets";
    } else if ("CAR".equals(kind)) {
      range = a.car();
      need = "applicant.car";
    } else {
      return unknown(c, "이 자산 기준은 직접 확인해 주세요");
    }
    if (range == null) return need(c, "자산을 넣으면 판정돼요", need);
    Status s = range.atMost(max * 10_000.0);
    return item(c, s, s == UNKNOWN ? Bands.BOUNDARY : reason(s, "자산이 기준을 넘어요"), List.of());
  }

  /**
   * 사는 곳이 그 지역이면 충족. 아니면 이사하면 받을 수 있어서 확인 필요예요 (찾아볼 지역의 혜택을 보여 주니까요). 일반구가 있는 시의 혜택은 그 구 주민도 사는
   * 곳이에요(재검토: 장안구 주민에게 수원시 혜택이 「이사하면 받을 수 있어요」로 나왔음).
   */
  private static Item residence(Condition c, Applicant a) {
    List<String> regions = strings(c, "regions");
    if (a.regionCode() != null
        && regions.stream()
            .anyMatch(
                r -> a.regionCode().startsWith(r) || CityDistricts.inCity(r, a.regionCode()))) {
      return item(c, MET, null, List.of());
    }
    return unknown(c, "이 지역으로 이사하면 받을 수 있어요");
  }

  private static Item homeless(Condition c, Applicant a, Integer minYears) {
    if (Boolean.TRUE.equals(a.homeOwner())) {
      return item(c, NOT_MET, "집이 있으면 받을 수 없어요", List.of());
    }
    if (a.homeOwner() == null) return need(c, "집이 있는지 넣으면 판정돼요", "applicant.homeOwner");
    if (minYears == null) return item(c, MET, null, List.of());
    if (a.homelessYears() == null) {
      return need(c, "무주택 기간을 넣으면 판정돼요", "applicant.homelessYears");
    }
    Status s = a.homelessYears().atLeast(minYears);
    return item(c, s, s == UNKNOWN ? Bands.BOUNDARY : reason(s, "무주택 기간이 모자라요"), List.of());
  }

  private static int yearOf(Applicant a, LocalDate today) {
    Integer year = a.incomeYearOf(MEDIAN);
    return year != null ? year : today.getYear();
  }

  private static String reason(Status s, String notMet) {
    return s == NOT_MET ? notMet : null;
  }

  private static Item unknown(Condition c, String why) {
    return item(c, UNKNOWN, why, List.of());
  }

  private static Item need(Condition c, String why, String input) {
    return item(c, UNKNOWN, why, List.of(input));
  }

  private static Item item(Condition c, Status s, String reason, List<String> needs) {
    return new Item(
        c.type() + "-" + c.group(), c.type(), c.rawText(), s, reason, needs, null, null, List.of());
  }

  private static Integer integer(Condition c, String key) {
    return c.value().get(key) instanceof Number n ? n.intValue() : null;
  }

  private static String text(Condition c, String key) {
    return c.value().get(key) instanceof String s ? s : null;
  }

  private static List<String> strings(Condition c, String key) {
    return c.value().get(key) instanceof Collection<?> list
        ? list.stream().map(String::valueOf).toList()
        : List.of();
  }
}
