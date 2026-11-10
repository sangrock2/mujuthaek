package kr.mujuthaek.api.eligibility.rule;

import static kr.mujuthaek.api.eligibility.rule.Status.MET;
import static kr.mujuthaek.api.eligibility.rule.Status.NOT_MET;
import static kr.mujuthaek.api.eligibility.rule.Status.UNKNOWN;
import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.util.List;
import kr.mujuthaek.api.eligibility.rule.Judgment.Basics;
import kr.mujuthaek.api.eligibility.rule.Judgment.Criterion;
import kr.mujuthaek.api.eligibility.rule.Judgment.Factor;
import org.junit.jupiter.api.Test;

class CriterionJudgeTest {

  static final LocalDate REF = LocalDate.of(2026, 10, 16);
  static final Basics B = new Basics("c1", "원문", 3, false, null);

  static ApplicantBuilder applicant() {
    return new ApplicantBuilder();
  }

  static Item judge(Criterion c, Applicant a) {
    return CriterionJudge.judge(c, a, REF);
  }

  @Test
  void ageFromTheBirthMonth() {
    var c = new Judgment.Age(B, 19, 39);
    // 기준일 2026-10-16: 1986년 11월생은 아직 39세, 1986년 9월생은 40세
    assertThat(judge(c, applicant().birthMonth(1986, 11).build()).status()).isEqualTo(MET);
    assertThat(judge(c, applicant().birthMonth(1986, 9).build()).status()).isEqualTo(NOT_MET);
    // 생일 달이면 일을 몰라서 39세일 수도 40세일 수도 있어요
    Item birthdayMonth = judge(c, applicant().birthMonth(1986, 10).build());
    assertThat(birthdayMonth.status()).isEqualTo(UNKNOWN);
    assertThat(birthdayMonth.reason()).contains("생일");
    // 생일 달이어도 두 나이 모두 기준 안이면 충족
    assertThat(judge(c, applicant().birthMonth(1997, 10).build()).status()).isEqualTo(MET);
    Item unknown = judge(c, Applicant.empty());
    assertThat(unknown.status()).isEqualTo(UNKNOWN);
    assertThat(unknown.needs()).containsExactly("applicant.birthDate");
    assertThat(unknown.reason()).isEqualTo("생년월일을 넣으면 판정돼요");
    assertThat(unknown.label()).isEqualTo("나이 · 만 19~39세");
    assertThat(unknown.evidence()).isEqualTo(new Item.Evidence("원문", 3));
  }

  @Test
  void ageFromTheBirthDateIsDecidedEvenInTheBirthdayMonth() {
    var c = new Judgment.Age(B, 19, 39);
    // 기준일 2026-10-16: 1986-10-16생은 그날 40세, 1986-10-17생은 아직 39세. 출생 연월로는 둘 다 확인 필요였어요
    assertThat(judge(c, applicant().birthDate(1986, 10, 16).build()).status()).isEqualTo(NOT_MET);
    Item notYet = judge(c, applicant().birthDate(1986, 10, 17).build());
    assertThat(notYet.status()).isEqualTo(MET);
    assertThat(notYet.reason()).isNull();
    // 생년월일이 있으면 출생 연월보다 먼저 써요
    assertThat(judge(c, applicant().birthDate(1986, 10, 17).birthMonth(1986, 10).build()).status())
        .isEqualTo(MET);
  }

  @Test
  void residenceComparesTheMeaningfulPartOfTheRegionCode() {
    var seoul = new Judgment.Residence(B, List.of("1100000000"), null);
    assertThat(judge(seoul, applicant().region("11440").build()).status()).isEqualTo(MET);
    assertThat(judge(seoul, applicant().region("41111").build()).status()).isEqualTo(NOT_MET);
    var dong = new Judgment.Residence(B, List.of("1144012000"), null);
    assertThat(judge(dong, applicant().region("11440").build()).status()).isEqualTo(UNKNOWN);
    var withMonths = new Judgment.Residence(B, List.of("1100000000"), 12);
    assertThat(judge(withMonths, applicant().region("11440").build()).status()).isEqualTo(UNKNOWN);
    assertThat(judge(withMonths, applicant().region("41111").build()).status()).isEqualTo(NOT_MET);
    // 일반구가 있는 시(2026-11-10 코드 검토): 수원시(41110)의 구는 앞부분이 4111x라 앞부분 일치만으로는 불충족이 됐음
    var suwon = new Judgment.Residence(B, List.of("4111000000"), null);
    assertThat(judge(suwon, applicant().region("41111").build()).status()).isEqualTo(MET);
    assertThat(judge(suwon, applicant().region("41280").build()).status()).isEqualTo(NOT_MET);
    var jangan = new Judgment.Residence(B, List.of("4111100000"), null);
    assertThat(judge(jangan, applicant().region("41110").build()).status()).isEqualTo(UNKNOWN);
    assertThat(judge(jangan, applicant().region("41000").build()).status()).isEqualTo(UNKNOWN);
    assertThat(judge(jangan, applicant().region("41113").build()).status()).isEqualTo(NOT_MET);
    assertThat(
            judge(
                    new Judgment.Residence(B, List.of("1111000000"), null),
                    applicant().region("11140").build())
                .status())
        .isEqualTo(NOT_MET); // 끝자리 0인 보통 구(종로구·중구)는 앞 네 자리가 달라 그대로
  }

  @Test
  void homelessYearsBand() {
    var any = new Judgment.Homeless(B, "HOUSEHOLD", null);
    var threeYears = new Judgment.Homeless(B, "HOUSEHOLD", 3);
    var twoYears = new Judgment.Homeless(B, "HOUSEHOLD", 2);
    assertThat(judge(any, applicant().homelessYears("LT_1").build()).status()).isEqualTo(MET);
    assertThat(judge(any, applicant().homeOwner(true).build()).status()).isEqualTo(NOT_MET);
    assertThat(judge(any, applicant().homeOwner(false).build()).status()).isEqualTo(MET);
    assertThat(judge(threeYears, applicant().homeOwner(false).build()).status()).isEqualTo(UNKNOWN);
    // 구간 경계(1·3·5년)와 같은 기준은 정확히
    assertThat(judge(threeYears, applicant().homelessYears("3_5").build()).status()).isEqualTo(MET);
    assertThat(judge(threeYears, applicant().homelessYears("1_3").build()).status())
        .isEqualTo(NOT_MET);
    // 구간 안쪽 기준(2년)은 1~3년이면 확인 필요
    Item between = judge(twoYears, applicant().homelessYears("1_3").build());
    assertThat(between.status()).isEqualTo(UNKNOWN);
    assertThat(between.reason()).isEqualTo(Bands.BOUNDARY);
    assertThat(judge(any, Applicant.empty()).needs()).containsExactly("applicant.homelessYears");
  }

  /** 테스트용 기준 월액: 도시근로자 2025년 1인 4,000,000원, 2인 5,000,000원 · 중위 2026년 1인 2,000,000원. */
  static final IncomeBenchmarks BENCHMARKS =
      (standard, year, size) -> {
        if ("URBAN_WORKER_INCOME".equals(standard) && year == 2025) {
          return size == 1 ? 4_000_000L : size == 2 ? 5_000_000L : null;
        }
        return "MEDIAN_INCOME".equals(standard) && year == 2026 && size == 1 ? 2_000_000L : null;
      };

  static Item judgeIncome(Judgment.Income c, Applicant a) {
    return CriterionJudge.judge(c, a, REF, BENCHMARKS);
  }

  @Test
  void incomeBandAgainstThePrintedMonthlyTable() {
    var c =
        new Judgment.Income(
            B,
            "HOUSEHOLD",
            "URBAN_WORKER_INCOME",
            2025,
            70.0,
            List.of(new Judgment.Bonus(new Factor("HOUSEHOLD_SIZE", 1, 1), 20)),
            "SUM",
            List.of(new Judgment.PrintedRow(1, 3_432_027), new Judgment.PrintedRow(2, 4_693_016)));
    String urban = "URBAN_WORKER_INCOME";

    // 80~85% × 4,000,000 = 3,200,000~3,400,000 ≤ 3,432,027
    Item ok = judgeIncome(c, applicant().household(1).income(urban, 80, 85).build());
    assertThat(ok.status()).isEqualTo(MET);
    assertThat(ok.threshold())
        .isEqualTo(new Item.Threshold("URBAN_WORKER_INCOME", 2025, 90.0, 1, 3_432_027L));
    assertThat(ok.label()).isEqualTo("소득 · 도시근로자 월평균소득 70% 이하");
    // 90~100% = 3,600,000~ → 넘어요
    assertThat(judgeIncome(c, applicant().household(1).income(urban, 90, 100).build()).status())
        .isEqualTo(NOT_MET);
    // 80~90% = 3,200,000~3,600,000 → 상한이 구간 안
    Item boundary = judgeIncome(c, applicant().household(1).income(urban, 80, 90).build());
    assertThat(boundary.status()).isEqualTo(UNKNOWN);
    assertThat(boundary.reason()).isEqualTo(Bands.BOUNDARY);
    // 2인인데 본인 소득만: 0~10% × 2인 5,000,000 = ~500,000 ≤ 4,693,016 → 가구 소득은 몰라서 원문 확인
    Item ownOnly = judgeIncome(c, applicant().household(2).income(urban, 0, 10).build());
    assertThat(ownOnly.status()).isEqualTo(UNKNOWN);
    assertThat(ownOnly.reason()).isEqualTo(Bands.HOUSEHOLD_INCOME_UNKNOWN);
    assertThat(ownOnly.needs()).isEmpty();
    // 본인 소득만 100~110% = 5,000,000~ → 가구 소득은 더 크니까 불충족
    Item ownOver = judgeIncome(c, applicant().household(2).income(urban, 100, 110).build());
    assertThat(ownOver.status()).isEqualTo(NOT_MET);
    assertThat(ownOver.reason()).isEqualTo(Bands.OWN_INCOME_OVER);
    // 소득을 아예 안 넣었으면 원문 확인
    Item noIncome = judgeIncome(c, applicant().household(2).build());
    assertThat(noIncome.status()).isEqualTo(UNKNOWN);
    assertThat(noIncome.reason()).isEqualTo(Bands.NO_INCOME);
    assertThat(noIncome.needs()).containsExactly("applicant.householdIncome");
    assertThat(
            judgeIncome(c, applicant().household(3).householdIncome(urban, 0, 10).build()).reason())
        .contains("세대원 수");
    assertThat(judgeIncome(c, applicant().income(urban, 0, 10).build()).needs())
        .containsExactly("applicant.householdSize");
  }

  @Test
  void incomeWithOnlyAPrintedTableUsesAnyBandWeCanConvert() {
    // 계약상 standard·percent가 null일 수 있어요 (공고 표만 있음). 예전엔 NPE로 맞춤 목록 전체가 500이었어요
    var c =
        new Judgment.Income(
            B,
            "HOUSEHOLD",
            null,
            2025,
            null,
            List.of(),
            "SUM",
            List.of(new Judgment.PrintedRow(1, 3_000_000)));
    Item ok =
        judgeIncome(c, applicant().household(1).income("URBAN_WORKER_INCOME", 60, 70).build());
    assertThat(ok.status()).isEqualTo(MET); // 2,400,000~2,800,000 ≤ 3,000,000
    assertThat(ok.label()).isEqualTo("소득 · 기준 소득 이하");
    // 바꿀 기준 월액이 없는 구간뿐이면 확인 필요
    assertThat(
            judgeIncome(c, applicant().household(1).income("MEDIAN_INCOME", 60, 70).build())
                .status())
        .isEqualTo(UNKNOWN);
  }

  @Test
  void incomeWithoutAPrintedTableWaitsForCriteria() {
    var c =
        new Judgment.Income(
            B, "APPLICANT", "MEDIAN_INCOME", 2026, 100.0, List.of(), "SUM", List.of());
    Item item = judge(c, applicant().household(1).income("MEDIAN_INCOME", 0, 10).build());
    assertThat(item.status()).isEqualTo(UNKNOWN);
    assertThat(item.reason()).contains("기준 금액");
  }

  @Test
  void incomeWithoutAPrintedTableUsesTheBenchmarkTimesThePercent() {
    // 기준 중위소득 100% (1인 가구 가산 +20%p → 120%), 기준 월액 2,000,000원 → 상한 2,400,000원
    var c =
        new Judgment.Income(
            B,
            "APPLICANT",
            "MEDIAN_INCOME",
            null,
            100.0,
            List.of(new Judgment.Bonus(new Factor("HOUSEHOLD_SIZE", 1, 1), 20)),
            "SUM",
            List.of());
    LocalDate ref = LocalDate.of(2026, 10, 22); // 판정 틀에 연도가 없으면 기준일의 연도
    String median = "MEDIAN_INCOME";

    Item ok =
        CriterionJudge.judge(
            c, applicant().household(1).income(median, 110, 120).build(), ref, BENCHMARKS);
    Item over =
        CriterionJudge.judge(
            c, applicant().household(1).income(median, 120, 130).build(), ref, BENCHMARKS);
    Item noTable =
        CriterionJudge.judge(
            c, applicant().household(2).income(median, 0, 10).build(), ref, BENCHMARKS);
    Item noBand =
        CriterionJudge.judge(
            c,
            applicant().household(1).income("URBAN_WORKER_INCOME", 0, 10).build(),
            ref,
            BENCHMARKS);

    assertThat(ok.status()).isEqualTo(MET);
    assertThat(ok.threshold())
        .isEqualTo(new Item.Threshold("MEDIAN_INCOME", 2026, 120.0, 1, 2_400_000L));
    assertThat(over.status()).isEqualTo(NOT_MET);
    assertThat(noTable.status()).isEqualTo(UNKNOWN);
    assertThat(noBand.needs()).containsExactly("applicant.income"); // 공고 기준 종류의 구간이 없어요
  }

  @Test
  void incomeBandFromAnotherYearIsConvertedWithThatYearsBenchmark() {
    // 공고는 2025년 기준, 사용자는 2026년 기준 월액으로 % 구간을 계산했어요 (incomeYear)
    // → 2026년 기준 월액으로 금액 구간을 만들어 2025년 상한과 비교해요
    var c =
        new Judgment.Income(
            B, "APPLICANT", "URBAN_WORKER_INCOME", 2025, 100.0, List.of(), "SUM", List.of());
    IncomeBenchmarks twoYears =
        (standard, year, size) ->
            !"URBAN_WORKER_INCOME".equals(standard) || size != 1
                ? null
                : year == 2025 ? 4_000_000L : year == 2026 ? 4_400_000L : null;
    // 2026년 기준 80~90% = 3,520,000~3,960,000 ≤ 2025년 상한 4,000,000
    Item item =
        CriterionJudge.judge(
            c,
            applicant().household(1).income("URBAN_WORKER_INCOME", 80, 90).incomeYear(2026).build(),
            REF,
            twoYears);
    assertThat(item.status()).isEqualTo(MET);
    // 기준 종류마다 연도를 따로 적으면 그 연도: 2025년 기준 95~100% = 3,800,000~4,000,000 ≤ 4,000,000
    Item perStandard =
        CriterionJudge.judge(
            c,
            applicant()
                .household(1)
                .income("URBAN_WORKER_INCOME", 95, 100)
                .incomeYear(2026)
                .incomeYear("URBAN_WORKER_INCOME", 2025)
                .build(),
            REF,
            twoYears);
    assertThat(perStandard.status()).isEqualTo(MET);
  }

  @Test
  void assetsAndCarsWithOverrides() {
    var assets =
        new Judgment.Asset(
            B,
            "HOUSEHOLD",
            245_000_000,
            List.of(new Judgment.Override(new Factor("CHILDREN", 2, null), 300_000_000)));
    assertThat(judge(assets, applicant().assets(245_000_000L).build()).status()).isEqualTo(MET);
    assertThat(judge(assets, applicant().assets(250_000_000L).children(2).build()).status())
        .isEqualTo(MET);
    assertThat(judge(assets, applicant().assets(250_000_000L).children(0).build()).status())
        .isEqualTo(NOT_MET);
    assertThat(judge(assets, applicant().assets(250_000_000L).build()).status()).isEqualTo(UNKNOWN);
    // 구간: 상한이 구간 안에 있으면 확인 필요, 구간이 다 넘으면 불충족
    Item boundary =
        judge(assets, applicant().assets(215_000_000L, 251_000_000L).children(0).build());
    assertThat(boundary.status()).isEqualTo(UNKNOWN);
    assertThat(boundary.reason()).isEqualTo(Bands.BOUNDARY);
    assertThat(judge(assets, applicant().assets(345_000_000L, null).children(0).build()).status())
        .isEqualTo(NOT_MET);
    assertThat(judge(assets, applicant().build()).needs()).containsExactly("applicant.assets");
    assertThat(judge(assets, applicant().build()).label()).isEqualTo("총자산 · 2억 4,500만 원 이하");

    var car = new Judgment.Car(B, 45_420_000, List.of());
    Item carItem = judge(car, applicant().car(45_420_001L).build());
    assertThat(carItem.key()).isEqualTo("CAR_VALUE");
    assertThat(carItem.status()).isEqualTo(NOT_MET);
    assertThat(carItem.label()).isEqualTo("자동차가액 · 4,542만 원 이하");
  }

  @Test
  void marriage() {
    var newlywed = new Judgment.Marriage(B, "MARRIED", 7, true);
    assertThat(judge(newlywed, applicant().married(2020, 1).build()).status()).isEqualTo(MET);
    assertThat(judge(newlywed, applicant().married(2019, 10).build()).status()).isEqualTo(NOT_MET);
    assertThat(judge(newlywed, applicant().marital("ENGAGED").build()).status()).isEqualTo(MET);
    assertThat(judge(newlywed, applicant().marital("SINGLE").build()).status()).isEqualTo(NOT_MET);
    assertThat(judge(newlywed, applicant().marital("MARRIED").build()).needs())
        .containsExactly("applicant.marriedOn");
    var single = new Judgment.Marriage(B, "NOT_MARRIED", null, false);
    assertThat(judge(single, applicant().marital("SINGLE").build()).status()).isEqualTo(MET);
    assertThat(judge(single, applicant().married(2020, 1).build()).status()).isEqualTo(NOT_MET);
  }

  @Test
  void childrenAndSavings() {
    var two = new Judgment.Children(B, 2, null, false);
    assertThat(judge(two, applicant().children(3).build()).status()).isEqualTo(MET);
    assertThat(judge(two, applicant().children(1).build()).status()).isEqualTo(NOT_MET);
    assertThat(
            judge(new Judgment.Children(B, 2, null, true), applicant().children(1).build())
                .status())
        .isEqualTo(UNKNOWN);
    assertThat(
            judge(new Judgment.Children(B, 1, 6, false), applicant().children(1).build()).status())
        .isEqualTo(UNKNOWN);

    var savings = new Judgment.Savings(B, 24, 24, null, null);
    assertThat(judge(savings, applicant().subscription("24_PLUS", 26).build()).status())
        .isEqualTo(MET);
    assertThat(judge(savings, applicant().subscription("12_24", 26).build()).status())
        .isEqualTo(NOT_MET);
    assertThat(judge(savings, applicant().subscription("24_PLUS", 10).build()).status())
        .isEqualTo(NOT_MET);
    assertThat(judge(savings, applicant().subscription("24_PLUS", null).build()).needs())
        .containsExactly("applicant.subscription.payments");
    // 지방 6개월 기준: 6개월~1년이면 충족, 6개월 미만이면 불충족
    var sixMonths = new Judgment.Savings(B, 6, null, null, null);
    assertThat(judge(sixMonths, applicant().subscription("6_12", null).build()).status())
        .isEqualTo(MET);
    assertThat(judge(sixMonths, applicant().subscription("LT_6", null).build()).status())
        .isEqualTo(NOT_MET);
    // 구간 안쪽 기준(18개월)은 1~2년이면 확인 필요
    assertThat(
            judge(
                    new Judgment.Savings(B, 18, null, null, null),
                    applicant().subscription("12_24", null).build())
                .status())
        .isEqualTo(UNKNOWN);
    // 통장이 없으면 어떤 청약통장 조건이든 불충족
    Item none =
        judge(
            new Judgment.Savings(B, null, null, null, null),
            applicant().subscription("NONE", null).build());
    assertThat(none.status()).isEqualTo(NOT_MET);
    assertThat(none.reason()).contains("청약통장이 있어야");
    assertThat(
            judge(
                    new Judgment.Savings(B, null, null, 3_000_000L, null),
                    applicant().subscription("12_24", 1).build())
                .status())
        .isEqualTo(UNKNOWN);
    assertThat(judge(savings, Applicant.empty()).needs())
        .containsExactly("applicant.subscription.months");
  }

  @Test
  void welfareStatuses() {
    var c = new Judgment.WelfareStatus(B, List.of("LIVELIHOOD_BENEFIT", "NEAR_POOR"));
    assertThat(judge(c, applicant().welfare("NEAR_POOR").build()).status()).isEqualTo(MET);
    assertThat(judge(c, applicant().welfare().build()).status()).isEqualTo(NOT_MET);
    assertThat(judge(c, Applicant.empty()).status()).isEqualTo(UNKNOWN);
    var disabled = new Judgment.WelfareStatus(B, List.of("DISABLED", "NEAR_POOR"));
    assertThat(judge(disabled, applicant().welfare().build()).status()).isEqualTo(UNKNOWN);
    // 기초생활수급자 입력은 생계·의료·주거·교육급여 중 무엇인지 몰라 생계급여 조건은 확인 필요(2026-11-10 코드 검토: 충족으로 판정했음)
    assertThat(judge(c, applicant().welfare("BASIC_LIVELIHOOD").build()).status())
        .isEqualTo(UNKNOWN);
    var housing = new Judgment.WelfareStatus(B, List.of("HOUSING_BENEFIT"));
    assertThat(judge(housing, applicant().welfare("BASIC_LIVELIHOOD").build()).status())
        .isEqualTo(UNKNOWN);
    assertThat(judge(housing, applicant().welfare("NEAR_POOR").build()).status())
        .isEqualTo(NOT_MET);
    var medical = new Judgment.WelfareStatus(B, List.of("MEDICAL_BENEFIT"));
    assertThat(judge(medical, applicant().welfare().build()).status())
        .isEqualTo(UNKNOWN); // 기초생활보장 밖 수급권자도 있음
    var student = new Judgment.WelfareStatus(B, List.of("UNIVERSITY_STUDENT"));
    assertThat(judge(student, applicant().targetGroups("UNIVERSITY_STUDENT").build()).status())
        .isEqualTo(MET);
  }

  @Test
  void askIsAlwaysToBeCheckedAndInReviewOnlyHoldsBackMet() {
    Item ask = judge(new Judgment.Ask(B, "예술인임을 증명할 수 있나요?", "YES"), Applicant.empty());
    assertThat(ask.status()).isEqualTo(UNKNOWN);
    assertThat(ask.reason()).isEqualTo("예술인임을 증명할 수 있나요?");

    var reviewing = new Judgment.Age(new Basics("c2", null, null, true, "나이 표기가 두 가지"), 19, 39);
    Item item = judge(reviewing, applicant().birthMonth(1997, 3).build());
    assertThat(item.status()).isEqualTo(UNKNOWN);
    assertThat(item.reason()).isNull(); // 검수 이유는 관리자용이라 회원 화면 문구로 내보내지 않아요
    assertThat(item.evidence()).isNull();
    // 검수 중이어도 입력만으로 걸리면 불충족 그대로 (2026-10-29 QA: 집 있는 사람이 무주택 조건에서 확인 필요로 남던 것)
    Item over = judge(reviewing, applicant().birthMonth(1980, 3).build());
    assertThat(over.status()).isEqualTo(NOT_MET);
    assertThat(over.reason()).isEqualTo("나이 기준에 맞지 않아요");
    // 입력이 없으면 지금처럼 확인 필요이고 입력을 따로 묻지 않아요
    Item empty = judge(reviewing, Applicant.empty());
    assertThat(empty.status()).isEqualTo(UNKNOWN);
    assertThat(empty.needs()).isEmpty();
  }

  @Test
  void exceptionBundleIsNamedByItsBaseCriterionAndLeavesExceptionsToTheSource() {
    // 2026-10-29 QA: 강북구 신혼부부의 무주택 예외 11가지가 이름 한 줄로 이어져 829자였어요
    var c =
        new Judgment.AnyOf(
            B,
            List.of(
                new Judgment.Option("기본 기준", List.of(new Judgment.Homeless(B, "HOUSEHOLD", null))),
                new Judgment.Option(
                    "상속으로 주택 공유지분을 취득했지만 부적격 통보일부터 3개월 이내에 처분하면 무주택으로 인정해요.",
                    List.of(new Judgment.Ask(B, "다음 예외에 해당하나요? 「상속으로 …」", "YES"))),
                new Judgment.Option(
                    "공고에 열거된 비수도권 오래된 단독주택은 무주택으로 인정해요.",
                    List.of(new Judgment.Ask(B, "다음 예외에 해당하나요? 「사용승인 후 20년 …」", "YES")))));

    Item owner = judge(c, applicant().homeOwner(true).build());
    assertThat(owner.label()).isEqualTo("무주택 · 세대 전원 (예외 2가지)");
    assertThat(owner.status()).isEqualTo(UNKNOWN);
    assertThat(owner.reason()).isEqualTo("예외에 해당하는지 원문을 확인해 주세요");
    assertThat(owner.options()).hasSize(3); // 길마다 이름과 결과는 그대로 줘요
    assertThat(judge(c, applicant().homeOwner(false).build()).status()).isEqualTo(MET);
    // 기본 기준을 아직 모르면 지금처럼 입력을 받아요
    Item empty = judge(c, Applicant.empty());
    assertThat(empty.reason()).isEqualTo("기준 중 하나에 맞는지 확인이 필요해요");
    assertThat(empty.needs()).isNotEmpty();
  }

  @Test
  void longAnyOfLabelShowsTheFirstOptionAndHowManyMore() {
    var youth = new Judgment.Age(B, 19, 39);
    var shortOne =
        new Judgment.AnyOf(
            B,
            List.of(
                new Judgment.Option("월평균소득 50% 이하", List.of(youth)),
                new Judgment.Option("월평균소득 50% 초과 ~100% 이하", List.of(youth))));
    assertThat(judge(shortOne, Applicant.empty()).label())
        .isEqualTo("다음 중 하나 · 월평균소득 50% 이하 / 월평균소득 50% 초과 ~100% 이하");

    var longOne =
        new Judgment.AnyOf(
            B,
            List.of(
                new Judgment.Option("자녀가 있고 같은 세대별 주민등록표등본에 자녀가 등재된 미성년 세대주", List.of(youth)),
                new Judgment.Option("형제자매를 부양해야 하는 미성년 세대주", List.of(youth)),
                new Judgment.Option("외국인 부모가 대리 신청하는 한부모가족", List.of(youth))));
    assertThat(judge(longOne, Applicant.empty()).label())
        .isEqualTo("다음 중 하나 · 자녀가 있고 같은 세대별 주민등록표등본에 자녀가 등재된 미성년 세대주 외 2가지");
  }

  @Test
  void wonLabels() {
    assertThat(Won.format(245_000_000)).isEqualTo("2억 4,500만 원");
    assertThat(Won.format(45_420_000)).isEqualTo("4,542만 원");
    assertThat(Won.format(2_669_354)).isEqualTo("266만 9,354원");
    assertThat(Won.format(0)).isEqualTo("0원");
  }
}
