package kr.mujuthaek.api.eligibility.rule;

import static kr.mujuthaek.api.eligibility.rule.Status.MET;
import static kr.mujuthaek.api.eligibility.rule.Status.NOT_MET;
import static kr.mujuthaek.api.eligibility.rule.Status.UNKNOWN;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import kr.mujuthaek.api.eligibility.rule.Judgment.Age;
import kr.mujuthaek.api.eligibility.rule.Judgment.AnyOf;
import kr.mujuthaek.api.eligibility.rule.Judgment.Ask;
import kr.mujuthaek.api.eligibility.rule.Judgment.Asset;
import kr.mujuthaek.api.eligibility.rule.Judgment.Car;
import kr.mujuthaek.api.eligibility.rule.Judgment.Children;
import kr.mujuthaek.api.eligibility.rule.Judgment.Criterion;
import kr.mujuthaek.api.eligibility.rule.Judgment.Factor;
import kr.mujuthaek.api.eligibility.rule.Judgment.Homeless;
import kr.mujuthaek.api.eligibility.rule.Judgment.Income;
import kr.mujuthaek.api.eligibility.rule.Judgment.Marriage;
import kr.mujuthaek.api.eligibility.rule.Judgment.Override;
import kr.mujuthaek.api.eligibility.rule.Judgment.PrintedRow;
import kr.mujuthaek.api.eligibility.rule.Judgment.Residence;
import kr.mujuthaek.api.eligibility.rule.Judgment.Savings;
import kr.mujuthaek.api.eligibility.rule.Judgment.WelfareStatus;
import kr.mujuthaek.api.eligibility.rule.frame.RegionCodes;

/**
 * 판정 틀의 조건 하나를 판정해요 (MET · NOT_MET · UNKNOWN).
 *
 * <p>입력이 비었거나, 검수 중(inReview)인데 불충족이 아니거나, 지금 입력 칸으로는 알 수 없는 조건(거주 기간, 청약 예치금, 부모 소득 …)은 UNKNOWN이고
 * 이유와 필요한 입력(needs)을 같이 줘요. 사용자가 보낸 값은 결과에 넣지 않아요.
 */
public final class CriterionJudge {

  private static final Map<String, String> INCOME_STANDARDS =
      Map.of(
          "MEDIAN_INCOME", "기준 중위소득",
          "URBAN_WORKER_INCOME", "도시근로자 월평균소득",
          "URBAN_WORKER_AVERAGE_INCOME", "도시근로자 가구당 월평균소득");

  /** 판정 틀의 수급 상태 중 판정 입력으로 알 수 있는 것과 그 입력 값. */
  private static final Map<String, String> WELFARE_INPUTS =
      Map.of(
          "NEAR_POOR", "NEAR_POOR",
          "SINGLE_PARENT", "SINGLE_PARENT");

  /**
   * 기초생활보장 급여 중 하나만 되는 상태. 입력 BASIC_LIVELIHOOD(기초생활수급자)는 생계·의료·주거·교육급여 중 무엇을 받는지 가리지 못해, 수급자면 확인
   * 필요이고 수급자가 아니면 이 급여도 아니에요. 생계급여 조건을 수급자 입력만으로 충족 처리하면 주거급여만 받는 사람이 영구임대 「생계·의료급여 수급자」 조건에서 지원
   * 가능이 됐어요(2026-11-10 코드 검토). 의료급여는 기초생활보장 밖의 수급권자(국가유공자 등)도 있어 입력으로 알 수 없어요.
   */
  private static final Set<String> BASIC_LIVELIHOOD_BENEFITS =
      Set.of("LIVELIHOOD_BENEFIT", "HOUSING_BENEFIT", "EDUCATION_BENEFIT");

  private static final String BASIC_LIVELIHOOD = "BASIC_LIVELIHOOD";

  private static final Set<String> TARGET_GROUP_STATUSES =
      Set.of("UNIVERSITY_STUDENT", "JOB_SEEKER");

  /** 추출은 예외를 「기본 기준」 길 하나 + 예외 길(원문 질문)들의 ANY_OF로 줘요 (extraction judgment/frame.py _exceptions). */
  private static final String BASE_OPTION = "기본 기준";

  /** 「다음 중 하나」 이름이 이보다 길면 첫 길과 나머지 수만 보여요. 길마다 이름과 결과는 options에 그대로 있어요. */
  private static final int ANY_OF_LABEL_MAX = 60;

  private CriterionJudge() {}

  public static Item judge(Criterion c, Applicant a, LocalDate referenceDate) {
    return judge(c, a, referenceDate, IncomeBenchmarks.NONE);
  }

  /**
   * @param benchmarks 인쇄된 소득표가 없을 때 쓰는 기준 소득 월액
   */
  public static Item judge(
      Criterion c, Applicant a, LocalDate referenceDate, IncomeBenchmarks benchmarks) {
    Item item =
        switch (c) {
          case Age x -> age(x, a, referenceDate);
          case Residence x -> residence(x, a);
          case Homeless x -> homeless(x, a, referenceDate);
          case Income x -> income(x, a, referenceDate, benchmarks);
          case Asset x ->
              limit(
                  x, "ASSET", "총자산", a.assets(), x.maxWon(), x.overrides(), a, "applicant.assets");
          case Car x ->
              limit(
                  x, "CAR_VALUE", "자동차가액", a.car(), x.maxWon(), x.overrides(), a, "applicant.car");
          case Marriage x -> marriage(x, a, referenceDate);
          case Children x -> children(x, a);
          case Savings x -> savings(x, a, referenceDate);
          case WelfareStatus x -> welfare(x, a);
          case AnyOf x -> anyOf(x, a, referenceDate, benchmarks);
          case Ask x -> item(x, "ASK", x.question(), UNKNOWN, x.question(), List.of(), null, null);
        };
    if (c.basics().inReview() && item.status() != NOT_MET) {
      // 검수 중이면 충족을 확인 필요로 낮춰요. 입력만으로 걸리는 불충족(집 있음, 나이 초과 …)은 그대로 둬요 (2026-10-29 QA).
      // 검수 이유(reviewReason)는 관리자용 설명이라 회원 화면에 문구로 보이지 않게 해요(2026-10-29 QA)
      return withStatus(item, UNKNOWN, null, List.of());
    }
    return item;
  }

  static Item age(Age c, Applicant a, LocalDate ref) {
    String label = "나이 · " + range("만 ", c.minAge(), c.maxAge(), "세");
    int[] ages = a.ages(ref);
    if (ages == null) {
      return item(
          c, "AGE", label, UNKNOWN, "생년월일을 넣으면 판정돼요", List.of("applicant.birthDate"), null, null);
    }
    Status status = Bands.ageWithin(ages, c.minAge(), c.maxAge());
    String reason =
        switch (status) {
          case MET -> null;
          case NOT_MET -> "나이 기준에 맞지 않아요";
          case UNKNOWN -> "생일이 지났는지에 따라 달라져요. 직접 확인해 주세요";
        };
    return item(c, "AGE", label, status, reason, List.of(), null, null);
  }

  static Item residence(Residence c, Applicant a) {
    String label = "거주지 · 공고 지역" + (c.minMonths() == null ? "" : " " + c.minMonths() + "개월 이상");
    if (a.regionCode() == null) {
      return item(
          c,
          "RESIDENCE",
          label,
          UNKNOWN,
          "사는 곳을 넣으면 판정돼요",
          List.of("applicant.regionCode"),
          null,
          null);
    }
    // 판정 틀 엔진과 같은 비교: 동 단위 조건·시도만 넣은 사용자·일반구가 있는 시(수원시 ↔ 장안구)
    Verdict where = RegionCodes.withinAny(a.regionCode(), c.regionCodes());
    if (where == Verdict.NOT_MET) {
      return item(c, "RESIDENCE", label, NOT_MET, "공고 지역에 살고 있지 않아요", List.of(), null, null);
    }
    if (where == Verdict.UNKNOWN) {
      return item(
          c, "RESIDENCE", label, UNKNOWN, "공고 지역에 드는지 더 자세한 주소로 확인이 필요해요", List.of(), null, null);
    }
    if (c.minMonths() != null) {
      return item(
          c, "RESIDENCE", label, UNKNOWN, "거주 기간은 공고 기준으로 직접 확인해 주세요", List.of(), null, null);
    }
    return item(c, "RESIDENCE", label, MET, null, List.of(), null, null);
  }

  static Item homeless(Homeless c, Applicant a, LocalDate ref) {
    String who = "HOUSEHOLD".equals(c.scope()) ? "세대 전원" : "본인";
    String label = "무주택 · " + who + (c.minYears() == null ? "" : " " + c.minYears() + "년 이상");
    if (Boolean.TRUE.equals(a.homeOwner())) {
      return item(c, "HOMELESS", label, NOT_MET, "집이 있으면 신청할 수 없어요", List.of(), null, null);
    }
    if (a.homelessYears() == null) {
      if (Boolean.FALSE.equals(a.homeOwner()) && c.minYears() == null) {
        return item(c, "HOMELESS", label, MET, null, List.of(), null, null);
      }
      return item(
          c,
          "HOMELESS",
          label,
          UNKNOWN,
          "무주택 기간을 넣으면 판정돼요",
          List.of("applicant.homelessYears"),
          null,
          null);
    }
    if (c.minYears() == null) {
      return item(c, "HOMELESS", label, MET, null, List.of(), null, null);
    }
    Status status = a.homelessYears().atLeast(c.minYears());
    String reason =
        switch (status) {
          case MET -> null;
          case NOT_MET -> "무주택 기간이 모자라요";
          case UNKNOWN -> Bands.BOUNDARY;
        };
    return item(c, "HOMELESS", label, status, reason, List.of(), null, null);
  }

  static Item income(Income c, Applicant a) {
    return income(c, a, null, IncomeBenchmarks.NONE);
  }

  /**
   * 소득: 상한 월액은 공고에 인쇄된 가구원 수별 표가 있으면 그걸, 없으면 기준 소득 월액 × 비율(가산 포함, 원 단위 버림)이에요. 사용자 소득은 기준 대비 % 구간으로
   * 받아서, 그 기준 연도의 기준 월액을 곱해 월 금액 구간으로 바꾼 뒤 상한과 비교해요.
   */
  static Item income(Income c, Applicant a, LocalDate ref, IncomeBenchmarks benchmarks) {
    // 공고 표만 있는 소득 조건은 기준 종류가 없어요 (계약: standard null). Map.of는 null 키를 못 찾아요
    String standard =
        c.standard() == null ? "기준 소득" : INCOME_STANDARDS.getOrDefault(c.standard(), "기준 소득");
    String label =
        "소득 · " + standard + (c.percent() == null ? "" : " " + number(c.percent()) + "%") + " 이하";
    Map<String, Bands.Range> bands;
    String need;
    switch (c.basis()) {
      case "APPLICANT" -> {
        bands = a.personalIncome();
        need = "applicant.income";
      }
      case "HOUSEHOLD" -> {
        bands = a.householdIncomeOrSelf();
        need = "applicant.householdIncome";
      }
      case "HOUSEHOLD_IF_HEAD" -> {
        if (!Boolean.TRUE.equals(a.householdHead())) {
          return item(
              c,
              "INCOME",
              label,
              UNKNOWN,
              "세대주인지 알려주면 판정돼요",
              List.of("applicant.householdHead"),
              null,
              null);
        }
        bands = a.householdIncomeOrSelf();
        need = "applicant.householdIncome";
      }
      default -> {
        return item(
            c, "INCOME", label, UNKNOWN, "부모 소득까지 합친 금액은 직접 확인해 주세요", List.of(), null, null);
      }
    }
    if (a.householdSize() == null) {
      return item(
          c,
          "INCOME",
          label,
          UNKNOWN,
          "세대원 수를 넣으면 판정돼요",
          List.of("applicant.householdSize"),
          null,
          null);
    }
    int size = a.householdSize();
    Double percent = effectivePercent(c, a);
    Integer year = c.year() != null ? c.year() : (ref == null ? null : ref.getYear());
    Long monthlyLimit = printedLimit(c.printedTable(), size);
    if (monthlyLimit == null
        && c.printedTable().isEmpty()
        && c.standard() != null
        && percent != null
        && year != null) {
      Long base = benchmarks.monthlyWon(c.standard(), year, size);
      monthlyLimit = base == null ? null : (long) Math.floor(base * percent / 100);
    }
    Item.Threshold threshold = new Item.Threshold(c.standard(), year, percent, size, monthlyLimit);
    if (monthlyLimit == null) {
      String why =
          c.printedTable().isEmpty() ? "그해 기준 금액을 아직 준비하지 못했어요" : "공고 표에 이 세대원 수의 기준 금액이 없어요";
      return item(c, "INCOME", label, UNKNOWN, why, List.of(), threshold, null);
    }
    String key = benchmarkKey(c.standard());
    Map<String, Bands.Range> own = a.personalIncome();
    if ((bands == null || bands.isEmpty())
        && !"APPLICANT".equals(c.basis())
        && own != null
        && !own.isEmpty()) {
      // 2인 이상인데 가구 소득 없이 본인 소득만 받았어요. 가구 소득은 본인 소득보다 작을 수 없어서
      // 본인 소득만으로 넘으면 불충족이고, 아니면 가구 소득을 따로 받지 않고 원문을 보게 해요 (2026-10-29 QA)
      Bands.Range ownMonthly = monthlyIncome(own, key, a, year, size, benchmarks);
      return ownMonthly != null && ownMonthly.atMost(monthlyLimit) == NOT_MET
          ? item(c, "INCOME", label, NOT_MET, Bands.OWN_INCOME_OVER, List.of(), threshold, null)
          : item(
              c,
              "INCOME",
              label,
              UNKNOWN,
              Bands.HOUSEHOLD_INCOME_UNKNOWN,
              List.of(),
              threshold,
              null);
    }
    if (bands == null || bands.isEmpty()) {
      return item(c, "INCOME", label, UNKNOWN, Bands.NO_INCOME, List.of(need), threshold, null);
    }
    Bands.Range monthly = monthlyIncome(bands, key, a, year, size, benchmarks);
    if (monthly == null) {
      return item(
          c,
          "INCOME",
          label,
          UNKNOWN,
          key != null && !bands.containsKey(key) ? Bands.NO_INCOME : "그해 기준 금액을 아직 준비하지 못했어요",
          key != null && !bands.containsKey(key) ? List.of(need) : List.of(),
          threshold,
          null);
    }
    Status status = monthly.atMost(monthlyLimit);
    String reason =
        switch (status) {
          case MET -> null;
          case NOT_MET -> "소득이 기준을 넘어요";
          case UNKNOWN -> Bands.BOUNDARY;
        };
    return item(c, "INCOME", label, status, reason, List.of(), threshold, null);
  }

  /** 받은 소득 % 구간을 월 금액 구간으로: 공고의 기준 종류로 받은 구간을 먼저, 없으면(공고 표만 있는 조건 등) 받은 다른 기준으로. */
  private static Bands.Range monthlyIncome(
      Map<String, Bands.Range> bands,
      String key,
      Applicant a,
      Integer year,
      int size,
      IncomeBenchmarks benchmarks) {
    for (String k : key == null ? bands.keySet() : List.of(key)) {
      Bands.Range pct = bands.get(k);
      Integer userYear = a.incomeYearOf(k) != null ? a.incomeYearOf(k) : year;
      Long base = pct == null || userYear == null ? null : benchmarks.monthlyWon(k, userYear, size);
      if (base != null) {
        return pct.times(base / 100.0);
      }
    }
    return null;
  }

  /** 판정 입력의 소득 구간 키 (도시근로자 소득 두 이름은 하나로). 기준 종류가 없으면 null. */
  static String benchmarkKey(String standard) {
    if (standard == null) {
      return null;
    }
    return "MEDIAN_INCOME".equals(standard) ? "MEDIAN_INCOME" : "URBAN_WORKER_INCOME";
  }

  /** 자산·자동차가액: 상한 이하. 조건(가구원 수·자녀 수)에 따라 상한이 바뀌면 큰 쪽을 써요. 값은 금액 구간이에요. */
  static Item limit(
      Criterion c,
      String key,
      String name,
      Bands.Range value,
      long maxWon,
      List<Override> overrides,
      Applicant a,
      String need) {
    String label = name + " · " + Won.format(maxWon) + " 이하";
    if (value == null) {
      return item(c, key, label, UNKNOWN, name + "을 넣으면 판정돼요", List.of(need), null, null);
    }
    long limit = maxWon;
    Long unknownLimit = null;
    for (Override o : overrides) {
      Boolean applies = applies(o.when(), a);
      if (Boolean.TRUE.equals(applies)) {
        limit = Math.max(limit, o.maxWon());
      } else if (applies == null) {
        unknownLimit = unknownLimit == null ? o.maxWon() : Math.max(unknownLimit, o.maxWon());
      }
    }
    Status status = value.atMost(limit);
    if (status == MET) {
      return item(c, key, label, MET, null, List.of(), null, null);
    }
    if (unknownLimit != null && unknownLimit > limit && value.atMost(unknownLimit) != NOT_MET) {
      return item(c, key, label, UNKNOWN, "기준이 달라지는 조건인지 확인이 필요해요", List.of(), null, null);
    }
    if (status == UNKNOWN) {
      return item(c, key, label, UNKNOWN, Bands.BOUNDARY, List.of(), null, null);
    }
    return item(c, key, label, NOT_MET, name + "이 기준을 넘어요", List.of(), null, null);
  }

  static Item marriage(Marriage c, Applicant a, LocalDate ref) {
    boolean married = "MARRIED".equals(c.require());
    String label =
        married
            ? "혼인 · "
                + (c.maxYears() == null ? "기혼" : "혼인 " + c.maxYears() + "년 이내")
                + (c.allowEngaged() ? " (예비 포함)" : "")
            : "혼인 · 미혼";
    if (a.marital() == null) {
      return item(
          c,
          "MARRIAGE",
          label,
          UNKNOWN,
          "혼인 상태를 넣으면 판정돼요",
          List.of("applicant.marital"),
          null,
          null);
    }
    if (!married) {
      boolean ok = !"MARRIED".equals(a.marital());
      return item(
          c, "MARRIAGE", label, ok ? MET : NOT_MET, ok ? null : "미혼이어야 해요", List.of(), null, null);
    }
    switch (a.marital()) {
      case "SINGLE" -> {
        return item(c, "MARRIAGE", label, NOT_MET, "혼인한 가구만 신청할 수 있어요", List.of(), null, null);
      }
      case "ENGAGED" -> {
        return c.allowEngaged()
            ? item(c, "MARRIAGE", label, MET, null, List.of(), null, null)
            : item(c, "MARRIAGE", label, NOT_MET, "예비 신혼부부는 신청할 수 없어요", List.of(), null, null);
      }
      default -> {
        if (c.maxYears() == null) {
          return item(c, "MARRIAGE", label, MET, null, List.of(), null, null);
        }
        if (a.marriedOn() == null) {
          return item(
              c,
              "MARRIAGE",
              label,
              UNKNOWN,
              "혼인신고 연월을 넣으면 판정돼요",
              List.of("applicant.marriedOn"),
              null,
              null);
        }
        // 혼인 연월만 알아서 그 달 1일(가장 긴 기간)과 말일(가장 짧은 기간)을 다 봐요: 둘 다 기준 안이면 충족, 둘 다 넘으면 불충족,
        // 갈리면 확인 필요(혜택 판정 BenefitJudge.newlywed와 같은 규칙). 예전엔 1일로만 봐서 경계 달이면 기준 안인 사람도
        // 「혼인 기간이 기준을 넘어요」가 됐어요(2026-11-11)
        int limit = c.maxYears() * 12;
        Status within =
            Periods.fullMonths(a.marriedOn(), ref) < limit
                ? MET
                : Periods.shortestFullMonths(a.marriedOn(), ref) >= limit ? NOT_MET : UNKNOWN;
        return item(
            c,
            "MARRIAGE",
            label,
            within,
            switch (within) {
              case MET -> null;
              case NOT_MET -> "혼인 기간이 기준을 넘어요";
              default -> Bands.BOUNDARY;
            },
            List.of(),
            null,
            null);
      }
    }
  }

  static Item children(Children c, Applicant a) {
    String label =
        "자녀 · "
            + (c.minCount() == null ? "자녀" : c.minCount() + "명 이상")
            + (c.youngestMaxAge() == null ? "" : " (막내 만 " + c.youngestMaxAge() + "세 이하)");
    if (a.children() == null) {
      return item(
          c,
          "CHILDREN",
          label,
          UNKNOWN,
          "자녀 수를 넣으면 판정돼요",
          List.of("applicant.children"),
          null,
          null);
    }
    if (c.minCount() != null && a.children() < c.minCount()) {
      return c.includeUnborn()
          ? item(
              c, "CHILDREN", label, UNKNOWN, "태아도 자녀로 세요. 해당하면 직접 확인해 주세요", List.of(), null, null)
          : item(c, "CHILDREN", label, NOT_MET, "자녀 수가 모자라요", List.of(), null, null);
    }
    if (c.youngestMaxAge() != null) {
      return item(c, "CHILDREN", label, UNKNOWN, "막내 자녀 나이를 직접 확인해 주세요", List.of(), null, null);
    }
    return item(c, "CHILDREN", label, MET, null, List.of(), null, null);
  }

  static Item savings(Savings c, Applicant a, LocalDate ref) {
    List<String> parts = new ArrayList<>();
    if (c.minMonths() != null) {
      parts.add("가입 " + c.minMonths() + "개월");
    }
    if (c.minPayments() != null) {
      parts.add("납입 " + c.minPayments() + "회");
    }
    if (c.minBalanceWon() != null) {
      parts.add("예치 " + Won.format(c.minBalanceWon()));
    }
    String label = "청약통장 · " + (parts.isEmpty() ? "보유" : String.join(" · ", parts) + " 이상");
    var s = a.subscription();
    if (s == null || s.months() == null) {
      return item(
          c,
          "SAVINGS",
          label,
          UNKNOWN,
          "청약통장 가입 기간을 넣으면 판정돼요",
          List.of("applicant.subscription.months"),
          null,
          null);
    }
    Status months = s.months().atLeast(c.minMonths() == null ? 0 : c.minMonths());
    if (months == NOT_MET) {
      return item(
          c,
          "SAVINGS",
          label,
          NOT_MET,
          s.months().none() ? "청약통장이 있어야 해요" : "가입 기간이 모자라요",
          List.of(),
          null,
          null);
    }
    if (c.minPayments() != null) {
      if (s.payments() == null) {
        return item(
            c,
            "SAVINGS",
            label,
            UNKNOWN,
            "납입 횟수를 넣으면 판정돼요",
            List.of("applicant.subscription.payments"),
            null,
            null);
      }
      if (s.payments() < c.minPayments()) {
        return item(c, "SAVINGS", label, NOT_MET, "납입 횟수가 모자라요", List.of(), null, null);
      }
    }
    if (months == UNKNOWN) {
      return item(c, "SAVINGS", label, UNKNOWN, Bands.BOUNDARY, List.of(), null, null);
    }
    if (c.minBalanceWon() != null || c.depositAreaM2() != null) {
      return item(c, "SAVINGS", label, UNKNOWN, "예치 금액은 청약통장에서 직접 확인해 주세요", List.of(), null, null);
    }
    return item(c, "SAVINGS", label, MET, null, List.of(), null, null);
  }

  static Item welfare(WelfareStatus c, Applicant a) {
    String label =
        "자격 · " + String.join(", ", c.anyOf().stream().map(CriterionJudge::statusName).toList());
    boolean answerable = true;
    for (String status : c.anyOf()) {
      if (BASIC_LIVELIHOOD_BENEFITS.contains(status)) {
        if (a.welfareStatuses() == null || a.welfareStatuses().contains(BASIC_LIVELIHOOD)) {
          answerable = false; // 수급자여도 어느 급여인지 몰라요
        }
      } else if (WELFARE_INPUTS.containsKey(status)) {
        if (a.welfareStatuses() == null) {
          answerable = false;
        } else if (a.welfareStatuses().contains(WELFARE_INPUTS.get(status))) {
          return item(c, "STATUS", label, MET, null, List.of(), null, null);
        }
      } else if (TARGET_GROUP_STATUSES.contains(status)) {
        if (a.targetGroups() == null) {
          answerable = false;
        } else if (a.targetGroups().contains(status)) {
          return item(c, "STATUS", label, MET, null, List.of(), null, null);
        }
      } else {
        answerable = false; // 장애인·국가유공자 등은 입력 칸이 없어요
      }
    }
    return answerable
        ? item(c, "STATUS", label, NOT_MET, "해당하는 자격이 없어요", List.of(), null, null)
        : item(
            c,
            "STATUS",
            label,
            UNKNOWN,
            "해당하는 자격이 있는지 확인이 필요해요",
            List.of("applicant.welfareStatuses"),
            null,
            null);
  }

  static Item anyOf(AnyOf c, Applicant a, LocalDate ref, IncomeBenchmarks benchmarks) {
    List<Item.OptionResult> options = new ArrayList<>();
    Set<String> needs = new LinkedHashSet<>();
    for (Judgment.Option o : c.options()) {
      List<Item> items = o.criteria().stream().map(x -> judge(x, a, ref, benchmarks)).toList();
      Status status = Status.all(items.stream().map(Item::status).toList());
      options.add(new Item.OptionResult(o.label(), status, items));
      if (status != NOT_MET) {
        items.forEach(i -> needs.addAll(i.needs()));
      }
    }
    Status status = Status.any(options.stream().map(Item.OptionResult::status).toList());
    boolean exceptions = options.size() > 1 && BASE_OPTION.equals(options.getFirst().label());
    String reason =
        switch (status) {
          case MET -> null;
          case NOT_MET -> "어느 기준에도 맞지 않아요";
          // 기본 기준에 걸리고 남은 건 드문 예외라 입력을 더 받지 않고 원문을 보게 해요 (2026-10-29 QA)
          case UNKNOWN ->
              exceptions && options.getFirst().status() == NOT_MET
                  ? "예외에 해당하는지 원문을 확인해 주세요"
                  : "기준 중 하나에 맞는지 확인이 필요해요";
        };
    return item(
        c,
        "ANY_OF",
        anyOfLabel(options, exceptions),
        status,
        reason,
        status == UNKNOWN ? List.copyOf(needs) : List.of(),
        null,
        options);
  }

  /**
   * 「다음 중 하나」 조건 이름. 예외 묶음이면 기본 기준 이름 + 예외 수, 아니면 길 이름을 잇되 길면 첫 길 + 나머지 수 (2026-10-29 QA: 무주택 예외
   * 11가지가 한 줄로 이어져 829자가 됐어요).
   */
  private static String anyOfLabel(List<Item.OptionResult> options, boolean exceptions) {
    int others = options.size() - 1;
    if (exceptions) {
      List<Item> base = options.getFirst().items();
      return (base.size() == 1 ? base.getFirst().label() : BASE_OPTION) + " (예외 " + others + "가지)";
    }
    String all =
        "다음 중 하나 · " + String.join(" / ", options.stream().map(Item.OptionResult::label).toList());
    return all.length() <= ANY_OF_LABEL_MAX || others == 0
        ? all
        : "다음 중 하나 · " + options.getFirst().label() + " 외 " + others + "가지";
  }

  /** 상한이 바뀌는 조건에 해당하는지. 입력으로 알 수 없으면 null. */
  static Boolean applies(Factor f, Applicant a) {
    Integer value =
        switch (f.factor()) {
          case "HOUSEHOLD_SIZE" -> a.householdSize();
          case "CHILDREN" -> a.children();
          default -> null; // NEWBORN_CHILDREN·DUAL_INCOME은 입력 칸이 없어요
        };
    if (value == null) {
      return null;
    }
    return (f.min() == null || value >= f.min()) && (f.max() == null || value <= f.max());
  }

  private static Long printedLimit(List<PrintedRow> table, int householdSize) {
    return table.stream()
        .filter(r -> r.householdSize() == householdSize)
        .map(PrintedRow::maxWon)
        .findFirst()
        .orElse(null);
  }

  /** 가구원 수 등에 따라 더해지는 비율까지 넣은 실제 비율 (화면 표시용). */
  private static Double effectivePercent(Income c, Applicant a) {
    if (c.percent() == null) {
      return null;
    }
    double added = 0;
    for (var b : c.bonuses()) {
      if (Boolean.TRUE.equals(applies(b.when(), a))) {
        added =
            "MAX".equals(c.bonusCombine())
                ? Math.max(added, b.addPercent())
                : added + b.addPercent();
      }
    }
    return c.percent() + added;
  }

  private static String statusName(String status) {
    return switch (status) {
      case "LIVELIHOOD_BENEFIT" -> "생계급여 수급자";
      case "MEDICAL_BENEFIT" -> "의료급여 수급자";
      case "HOUSING_BENEFIT" -> "주거급여 수급자";
      case "EDUCATION_BENEFIT" -> "교육급여 수급자";
      case "NEAR_POOR" -> "차상위계층";
      case "SINGLE_PARENT" -> "한부모가족";
      case "DISABLED" -> "장애인";
      case "NATIONAL_MERIT" -> "국가유공자";
      case "NORTH_KOREAN_DEFECTOR" -> "북한이탈주민";
      case "FACILITY_LEAVER" -> "보호시설 퇴소자";
      case "UNIVERSITY_STUDENT" -> "대학생";
      case "JOB_SEEKER" -> "취업준비생";
      default -> status;
    };
  }

  private static String range(String prefix, Integer min, Integer max, String unit) {
    if (min != null && max != null) {
      return prefix + min + "~" + max + unit;
    }
    if (min != null) {
      return prefix + min + unit + " 이상";
    }
    if (max != null) {
      return prefix + max + unit + " 이하";
    }
    return "제한 없음";
  }

  private static String number(double value) {
    return value == Math.rint(value) ? String.valueOf((long) value) : String.valueOf(value);
  }

  private static Item item(
      Criterion c,
      String key,
      String label,
      Status status,
      String reason,
      List<String> needs,
      Item.Threshold threshold,
      List<Item.OptionResult> options) {
    var b = c.basics();
    Item.Evidence evidence = b.quote() == null ? null : new Item.Evidence(b.quote(), b.page());
    return new Item(b.id(), key, label, status, reason, needs, threshold, evidence, options);
  }

  private static Item withStatus(Item i, Status status, String reason, List<String> needs) {
    return new Item(
        i.id(),
        i.key(),
        i.label(),
        status,
        reason,
        needs,
        i.threshold(),
        i.evidence(),
        i.options());
  }
}
