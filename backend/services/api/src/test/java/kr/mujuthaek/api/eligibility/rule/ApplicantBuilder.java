package kr.mujuthaek.api.eligibility.rule;

import java.time.LocalDate;
import java.time.YearMonth;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import kr.mujuthaek.api.eligibility.rule.Bands.Range;

/** 테스트용 판정 입력. 넣지 않은 칸은 비어 있어요(null). */
public final class ApplicantBuilder {

  private LocalDate birthDate;
  private YearMonth birthMonth;
  private String regionCode;
  private Boolean householdHead;
  private Integer householdSize;
  private Integer dependents;
  private List<String> targetGroups;
  private String marital;
  private YearMonth marriedOn;
  private Integer children;
  private Boolean homeOwner;
  private Bands.Span homelessYears;
  private Applicant.Subscription subscription;
  private List<String> welfareStatuses;
  private Map<String, Range> personalIncome;
  private Map<String, Range> householdIncome;
  private Integer incomeYear;
  private Map<String, Integer> incomeYears;
  private Range assets;
  private Range car;
  private List<String> rankChecks;

  public ApplicantBuilder birthDate(int y, int m, int d) {
    birthDate = LocalDate.of(y, m, d);
    return this;
  }

  public ApplicantBuilder birthMonth(int y, int m) {
    birthMonth = YearMonth.of(y, m);
    return this;
  }

  public ApplicantBuilder region(String code) {
    regionCode = code;
    return this;
  }

  public ApplicantBuilder head(boolean value) {
    householdHead = value;
    return this;
  }

  public ApplicantBuilder household(int size) {
    householdSize = size;
    return this;
  }

  public ApplicantBuilder dependents(int n) {
    dependents = n;
    return this;
  }

  public ApplicantBuilder targetGroups(String... groups) {
    targetGroups = List.of(groups);
    return this;
  }

  public ApplicantBuilder marital(String value) {
    marital = value;
    return this;
  }

  public ApplicantBuilder married(int y, int m) {
    marital = "MARRIED";
    marriedOn = YearMonth.of(y, m);
    return this;
  }

  public ApplicantBuilder children(int n) {
    children = n;
    return this;
  }

  /** 무주택 기간 구간: LT_1 · 1_3 · 3_5 · 5_PLUS. */
  public ApplicantBuilder homelessYears(String band) {
    homeOwner = false;
    homelessYears = Bands.HOMELESS_YEARS.get(band);
    return this;
  }

  public ApplicantBuilder homeOwner(boolean value) {
    homeOwner = value;
    return this;
  }

  /** 청약 가입 기간 구간(NONE · LT_6 · 6_12 · 12_24 · 24_PLUS)과 납입 횟수. */
  public ApplicantBuilder subscription(String months, Integer payments) {
    subscription = new Applicant.Subscription(Bands.SUBSCRIPTION_MONTHS.get(months), payments);
    return this;
  }

  public ApplicantBuilder welfare(String... statuses) {
    welfareStatuses = List.of(statuses);
    return this;
  }

  /** 본인 소득의 기준 대비 % 구간 (gt 초과 ~ le 이하). */
  public ApplicantBuilder income(String standard, Integer gtPct, Integer lePct) {
    personalIncome = put(personalIncome, standard, gtPct, lePct);
    return this;
  }

  public ApplicantBuilder householdIncome(String standard, Integer gtPct, Integer lePct) {
    householdIncome = put(householdIncome, standard, gtPct, lePct);
    return this;
  }

  public ApplicantBuilder incomeYear(int year) {
    incomeYear = year;
    return this;
  }

  /** 이 기준 종류만 다른 연도로 계산했을 때 (도시근로자 소득은 보통 전해 값). */
  public ApplicantBuilder incomeYear(String standard, int year) {
    incomeYears = incomeYears == null ? new LinkedHashMap<>() : new LinkedHashMap<>(incomeYears);
    incomeYears.put(standard, year);
    return this;
  }

  /** 정확히 이 금액 (구간 won-1 초과 ~ won 이하). */
  public ApplicantBuilder assets(long won) {
    assets = new Range(won - 1, won);
    return this;
  }

  public ApplicantBuilder assets(Long gtWon, Long leWon) {
    assets = new Range(gtWon, leWon);
    return this;
  }

  /** 정확히 이 금액. */
  public ApplicantBuilder car(long won) {
    car = new Range(won - 1, won);
    return this;
  }

  public ApplicantBuilder rankChecks(String... keys) {
    rankChecks = List.of(keys);
    return this;
  }

  private static Map<String, Range> put(
      Map<String, Range> map, String standard, Integer gt, Integer le) {
    Map<String, Range> out = map == null ? new LinkedHashMap<>() : new LinkedHashMap<>(map);
    out.put(
        standard,
        new Range(gt == null ? null : gt.longValue(), le == null ? null : le.longValue()));
    return out;
  }

  public Applicant build() {
    return new Applicant(
        birthDate,
        birthMonth,
        regionCode,
        householdHead,
        householdSize,
        dependents,
        targetGroups,
        marital,
        marriedOn,
        children,
        homeOwner,
        homelessYears,
        subscription,
        welfareStatuses,
        personalIncome,
        householdIncome,
        incomeYear,
        incomeYears,
        assets,
        car,
        rankChecks);
  }
}
