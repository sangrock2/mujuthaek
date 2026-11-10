package kr.mujuthaek.api.eligibility.rule.frame;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.YearMonth;
import java.util.List;
import java.util.Map;
import java.util.OptionalLong;
import java.util.Set;
import kr.mujuthaek.api.eligibility.rule.BaseValues;
import kr.mujuthaek.api.eligibility.rule.Eligibility;
import kr.mujuthaek.api.eligibility.rule.Field;
import kr.mujuthaek.api.eligibility.rule.Verdict;
import kr.mujuthaek.api.eligibility.rule.frame.Applicant.BusinessRecord;
import kr.mujuthaek.api.eligibility.rule.frame.Applicant.Household;
import kr.mujuthaek.api.eligibility.rule.frame.Applicant.MaritalStatus;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.Meta;
import org.junit.jupiter.api.Test;

/** 정답 케이스가 덜 건드리는 규칙의 경계: 조건 종류마다 충족·불충족·확인 필요가 갈리는 지점을 봐요. */
class RulesTest {

  private static final LocalDate DAY = LocalDate.of(2026, 10, 1);

  private static Meta meta(String id) {
    return new Meta(id, null, null, false, null, null);
  }

  private static Applicant applicant(
      LocalDate birth,
      String residence,
      MaritalStatus marital,
      LocalDate marriedOn,
      List<LocalDate> children,
      Boolean expecting,
      Household household,
      Applicant.Subscription subscription,
      Applicant.Business business) {
    return new Applicant(
        birth,
        null,
        residence,
        null,
        marital,
        marriedOn,
        children,
        expecting,
        household,
        subscription,
        business,
        null,
        null,
        Map.of());
  }

  private static Applicant withBusiness(Applicant.Business business) {
    return applicant(null, null, null, null, null, null, null, null, business);
  }

  private static Applicant.Business business(
      Boolean hasSite, String site, List<BusinessRecord> history, String industry) {
    return new Applicant.Business(null, hasSite, site, history, industry, null);
  }

  private static BusinessRecord record(String opened, String closed) {
    return new BusinessRecord(
        LocalDate.parse(opened), closed == null ? null : LocalDate.parse(closed));
  }

  private static Household household(Integer size, Boolean homeless, Integer homelessYears) {
    return new Household(
        size, null, homeless, null, homelessYears, null, null, null, null, null, null, null, null);
  }

  // ── 사람 ──

  private static Applicant korean(Boolean korean) {
    return new Applicant(
        null, korean, null, null, null, null, null, null, null, null, null, null, null, Map.of());
  }

  @Test
  void nationalityOnlyAsksWhetherTheApplicantIsKorean() {
    Criterion.Nationality koreansOnly = new Criterion.Nationality(meta("n"), List.of("KR"));
    assertThat(PersonRules.nationality(koreansOnly, korean(true)).verdict()).isEqualTo(Verdict.MET);
    assertThat(PersonRules.nationality(koreansOnly, korean(false)).verdict())
        .isEqualTo(Verdict.NOT_MET);
    Evaluation unanswered = PersonRules.nationality(koreansOnly, korean(null));
    assertThat(unanswered.verdict()).isEqualTo(Verdict.UNKNOWN);
    assertThat(unanswered.missing()).containsExactly(Input.KOREAN);

    // 다른 나라 국적도 받는 틀: 국민이 아니면 어느 나라인지 몰라서 확인 필요, KR이 없으면 국민은 불충족
    Criterion.Nationality alsoUs = new Criterion.Nationality(meta("n"), List.of("KR", "US"));
    assertThat(PersonRules.nationality(alsoUs, korean(false)).verdict()).isEqualTo(Verdict.UNKNOWN);
    Criterion.Nationality usOnly = new Criterion.Nationality(meta("n"), List.of("US"));
    assertThat(PersonRules.nationality(usOnly, korean(true)).verdict()).isEqualTo(Verdict.NOT_MET);
  }

  @Test
  void residenceOrBusinessSiteNeedsOnlyOneToMatch() {
    Criterion.Region either =
        new Criterion.Region(
            meta("r"), Criterion.RegionBasis.RESIDENCE_OR_BUSINESS_SITE, List.of("2700000000"));
    Applicant livesInDaegu =
        applicant(
            null,
            "2729000000",
            null,
            null,
            null,
            null,
            null,
            null,
            business(false, null, null, null));
    assertThat(PersonRules.region(either, livesInDaegu).verdict()).isEqualTo(Verdict.MET);

    Applicant noSiteElsewhere =
        applicant(
            null,
            "1100000000",
            null,
            null,
            null,
            null,
            null,
            null,
            business(false, null, null, null));
    assertThat(PersonRules.region(either, noSiteElsewhere).verdict()).isEqualTo(Verdict.NOT_MET);

    Evaluation unknown = PersonRules.region(either, Applicant.empty());
    assertThat(unknown.verdict()).isEqualTo(Verdict.UNKNOWN);
    assertThat(unknown.missing()).containsExactly(Input.RESIDENCE_REGION, Input.BUSINESS_SITE);
  }

  @Test
  void residenceMonthsAreComparedOnlyAfterThePlaceMatches() {
    Criterion.Residence c = new Criterion.Residence(meta("r"), List.of("1100000000"), 12);
    Applicant seoulNoMonths =
        applicant(null, "1168000000", null, null, null, null, null, null, null);
    assertThat(PersonRules.residence(c, seoulNoMonths).missing())
        .containsExactly(Input.RESIDENCE_MONTHS);
    Applicant busan = applicant(null, "2600000000", null, null, null, null, null, null, null);
    assertThat(PersonRules.residence(c, busan).verdict()).isEqualTo(Verdict.NOT_MET);
  }

  @Test
  void notMarriedMeansNotCurrentlyMarried() {
    Criterion.Marriage c =
        new Criterion.Marriage(meta("m"), Criterion.MarriageRequirement.NOT_MARRIED, null, false);
    assertThat(
            PersonRules.marriage(
                    c,
                    applicant(
                        null, null, MaritalStatus.DIVORCED, null, null, null, null, null, null),
                    DAY)
                .verdict())
        .isEqualTo(Verdict.MET);
    assertThat(
            PersonRules.marriage(
                    c,
                    applicant(
                        null, null, MaritalStatus.MARRIED, null, null, null, null, null, null),
                    DAY)
                .verdict())
        .isEqualTo(Verdict.NOT_MET);
  }

  private static Applicant bornIn(String month) {
    return new Applicant(
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        Map.of(),
        YearMonth.parse(month));
  }

  @Test
  void ageFromBirthMonthIsDecidedUnlessTheBirthdayFallsInTheReferenceMonth() {
    Criterion.Age youth = new Criterion.Age(meta("youth-age"), 19, 39);
    // 기준일 2026-10-01: 1987-09생은 그 달 어느 날이든 만 39세 → 충족
    assertThat(PersonRules.age(youth, bornIn("1987-09"), DAY).verdict()).isEqualTo(Verdict.MET);
    // 1986-09생은 그 달 어느 날이든 만 40세 → 불충족
    assertThat(PersonRules.age(youth, bornIn("1986-09"), DAY).verdict()).isEqualTo(Verdict.NOT_MET);
    // 1986-10생은 10월 1일생이면 만 40세, 2일 이후면 만 39세 → 확인 필요. 화면은 출생 연월만 보내서 생년월일을 묻지 않아요
    var edge = PersonRules.age(youth, bornIn("1986-10"), DAY);
    assertThat(edge.verdict()).isEqualTo(Verdict.UNKNOWN);
    assertThat(edge.reason()).isEqualTo("생일이 지났는지에 따라 달라져요. 직접 확인해 주세요");
    assertThat(edge.missing()).isEmpty();
  }

  @Test
  void marriageWithinYearsNeedsTheRegistrationDate() {
    Criterion.Marriage c =
        new Criterion.Marriage(meta("m"), Criterion.MarriageRequirement.MARRIED, 7, false);
    Applicant noDate =
        applicant(null, null, MaritalStatus.MARRIED, null, null, null, null, null, null);
    assertThat(PersonRules.marriage(c, noDate, DAY).missing()).containsExactly(Input.MARRIED_ON);
    // 2019-10-01 + 7년 = 2026-10-01 (기준일과 같은 날) → 충족
    Applicant edge =
        applicant(
            null,
            null,
            MaritalStatus.MARRIED,
            LocalDate.of(2019, 10, 1),
            null,
            null,
            null,
            null,
            null);
    assertThat(PersonRules.marriage(c, edge, DAY).verdict()).isEqualTo(Verdict.MET);
    Applicant engaged =
        applicant(null, null, MaritalStatus.ENGAGED, null, null, null, null, null, null);
    assertThat(PersonRules.marriage(c, engaged, DAY).verdict())
        .as("예비신혼 불포함")
        .isEqualTo(Verdict.NOT_MET);
  }

  @Test
  void anUnknownPregnancyMattersOnlyWhenItChangesTheResult() {
    Criterion.Children twoKids = new Criterion.Children(meta("c"), 2, null, true);
    Applicant oneChild =
        applicant(
            null, null, null, null, List.of(LocalDate.of(2020, 1, 1)), null, null, null, null);
    Evaluation e = PersonRules.children(twoKids, oneChild, DAY);
    assertThat(e.verdict()).isEqualTo(Verdict.UNKNOWN);
    assertThat(e.missing()).containsExactly(Input.EXPECTING_CHILD);

    Applicant threeChildren =
        applicant(
            null,
            null,
            null,
            null,
            List.of(LocalDate.of(2015, 1, 1), LocalDate.of(2018, 1, 1), LocalDate.of(2020, 1, 1)),
            null,
            null,
            null,
            null);
    assertThat(PersonRules.children(twoKids, threeChildren, DAY).verdict()).isEqualTo(Verdict.MET);

    Applicant adultChildren =
        applicant(
            null, null, null, null, List.of(LocalDate.of(2000, 1, 1)), false, null, null, null);
    assertThat(PersonRules.children(twoKids, adultChildren, DAY).verdict())
        .as("성인 자녀는 미성년 자녀로 세지 않아요")
        .isEqualTo(Verdict.NOT_MET);
  }

  // ── 주거 ──

  @Test
  void homelessYearsAreNeededOnlyWhenHomeless() {
    Criterion.Homeless c = new Criterion.Homeless(meta("h"), Criterion.HomelessScope.HOUSEHOLD, 2);
    assertThat(
            HousingRules.homeless(
                    c,
                    applicant(
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        household(null, true, null),
                        null,
                        null))
                .missing())
        .containsExactly(Input.HOMELESS_YEARS);
    assertThat(
            HousingRules.homeless(
                    c,
                    applicant(
                        null, null, null, null, null, null, household(null, true, 3), null, null))
                .verdict())
        .isEqualTo(Verdict.MET);
    assertThat(
            HousingRules.homeless(
                    c,
                    applicant(
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        household(null, false, null),
                        null,
                        null))
                .verdict())
        .isEqualTo(Verdict.NOT_MET);
  }

  /** 기준값 표가 비어 있는 주거 규칙 (청약통장처럼 표가 필요 없는 조건을 볼 때). */
  private static final HousingRules NO_TABLES =
      new HousingRules(
          (k, y, p, s) -> OptionalLong.empty(), (d, region, area) -> OptionalLong.empty());

  private static final LocalDate SAVINGS_DAY = LocalDate.of(2026, 10, 16);

  @Test
  void savingsWithoutMinimumsOnlyNeedAnAccount() {
    Criterion.Savings c = new Criterion.Savings(meta("s"), null, null, null, null);
    assertThat(NO_TABLES.savings(c, Applicant.empty(), SAVINGS_DAY).missing())
        .containsExactly(Input.SUBSCRIPTION_MONTHS);
    Applicant none =
        applicant(
            null, null, null, null, null, null, null, new Applicant.Subscription(0, 0, 0L), null);
    assertThat(NO_TABLES.savings(c, none, SAVINGS_DAY).verdict()).isEqualTo(Verdict.NOT_MET);
  }

  @Test
  void aKnownFailingSavingsRuleDecidesEvenIfOthersAreUnknown() {
    Criterion.Savings c = new Criterion.Savings(meta("s"), 24, 24, 3_000_000L, null);
    Applicant shortAccount =
        applicant(
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            new Applicant.Subscription(6, null, null),
            null);
    assertThat(NO_TABLES.savings(c, shortAccount, SAVINGS_DAY).verdict())
        .isEqualTo(Verdict.NOT_MET);
  }

  @Test
  void applicantAndParentsIncomeUsesTheirOwnHouseholdSize() {
    // 기준값 4인 600만원 × 100% = 600만원. 가산은 MAX: 맞벌이 미입력이라 가산 없이 판정해 봐요
    BaseValues table =
        (kind, year, program, size) ->
            size == 4 ? OptionalLong.of(6_000_000) : OptionalLong.empty();
    HousingRules rules = new HousingRules(table, (d, region, area) -> OptionalLong.empty());
    Criterion.Income c =
        new Criterion.Income(
            meta("i"),
            Criterion.IncomeBasis.APPLICANT_AND_PARENTS,
            Criterion.IncomeStandard.MEDIAN_INCOME,
            2026,
            BigDecimal.valueOf(100),
            List.of(
                new Criterion.Bonus(
                    new Criterion.Factor(Criterion.FactorKind.DUAL_INCOME, null, null, null, null),
                    BigDecimal.TEN)),
            Criterion.BonusCombine.MAX,
            List.of());
    Household parentsMissing =
        new Household(
            null, null, null, null, null, null, 2_000_000L, null, 4, null, null, null, null);
    Evaluation missing =
        rules.income(
            c, applicant(null, null, null, null, null, null, parentsMissing, null, null), DAY);
    assertThat(missing.missing()).containsExactly(Input.PARENTS_INCOME);

    Household both =
        new Household(
            null, null, null, null, null, null, 2_000_000L, 3_500_000L, 4, null, null, null, null);
    Evaluation within =
        rules.income(c, applicant(null, null, null, null, null, null, both, null, null), DAY);
    assertThat(within.verdict()).as("550만원 ≤ 600만원").isEqualTo(Verdict.MET);
  }

  // ── 사업 ──

  @Test
  void closureAnyNeedsAClosureInThePeriod() {
    Criterion.Closure any =
        new Criterion.Closure(meta("c"), Criterion.ClosureMode.ANY, LocalDate.of(2020, 1, 1), null);
    assertThat(
            BusinessRules.closure(
                    any,
                    withBusiness(
                        business(null, null, List.of(record("2015-01-01", "2021-05-05")), null)),
                    DAY)
                .verdict())
        .isEqualTo(Verdict.MET);
    assertThat(
            BusinessRules.closure(any, withBusiness(business(null, null, List.of(), null)), DAY)
                .verdict())
        .isEqualTo(Verdict.NOT_MET);
  }

  @Test
  void closedWithoutAPeriodMeansAnyPastClosure() {
    Criterion.BusinessRegistration closed =
        new Criterion.BusinessRegistration(
            meta("b"), Criterion.RegistrationRequirement.CLOSED, null);
    assertThat(
            BusinessRules.registration(
                    closed,
                    withBusiness(
                        business(null, null, List.of(record("2001-01-01", "2003-01-01")), null)),
                    DAY)
                .verdict())
        .isEqualTo(Verdict.MET);
    assertThat(
            BusinessRules.registration(
                    closed,
                    withBusiness(
                        business(
                            null,
                            null,
                            List.of(record("2001-01-01", "2003-01-01"), record("2024-01-01", null)),
                            null)),
                    DAY)
                .verdict())
        .as("지금 영업 중이면 불충족")
        .isEqualTo(Verdict.NOT_MET);
  }

  @Test
  void revenueWithOnlyAMinimum() {
    Criterion.Revenue c = new Criterion.Revenue(meta("r"), 2025, 100_000_000L, null);
    Applicant.Business enough =
        new Applicant.Business(null, null, null, null, null, Map.of(2025, 150_000_000L));
    assertThat(BusinessRules.revenue(c, withBusiness(enough)).verdict()).isEqualTo(Verdict.MET);
    Applicant.Business otherYear =
        new Applicant.Business(null, null, null, null, null, Map.of(2024, 150_000_000L));
    assertThat(BusinessRules.revenue(c, withBusiness(otherYear)).missing())
        .containsExactly(Input.REVENUE);
  }

  @Test
  void onlyIndustriesHaveThreeOutcomes() {
    Criterion.Industry only =
        new Criterion.Industry(
            meta("i"), Criterion.IndustryMode.ONLY, 11, List.of("58"), List.of("62"));
    assertThat(
            BusinessRules.industry(only, withBusiness(business(null, null, null, "58222")))
                .verdict())
        .isEqualTo(Verdict.MET);
    assertThat(
            BusinessRules.industry(only, withBusiness(business(null, null, null, "62010")))
                .verdict())
        .isEqualTo(Verdict.UNKNOWN);
    assertThat(
            BusinessRules.industry(only, withBusiness(business(null, null, null, "56111")))
                .verdict())
        .isEqualTo(Verdict.NOT_MET);
    Criterion.Industry oldRevision =
        new Criterion.Industry(
            meta("o"), Criterion.IndustryMode.EXCLUDE, 10, List.of("56211"), List.of());
    assertThat(
            BusinessRules.industry(oldRevision, withBusiness(business(null, null, null, "58222")))
                .verdict())
        .as("10차 공고는 11차 코드와 바로 비교하지 않아요")
        .isEqualTo(Verdict.UNKNOWN);
  }

  @Test
  void applicantTypeComparesIndividualOrCorporation() {
    Criterion.ApplicantKind corporation =
        new Criterion.ApplicantKind(meta("a"), Applicant.ApplicantType.CORPORATION);
    assertThat(BusinessRules.applicantKind(corporation, Applicant.empty()).missing())
        .containsExactly(Input.APPLICANT_TYPE);
  }

  @Test
  void inReviewHoldsBackMetButKeepsNotMet() {
    Criterion.Age reviewing =
        new Criterion.Age(new Meta("youth-age", null, null, true, "나이 표기가 두 가지", null), 19, 39);
    FrameJudge judge =
        new FrameJudge(
            (k, y, p, s) -> OptionalLong.empty(), (d, region, area) -> OptionalLong.empty());
    var met = judge.evaluate(reviewing, bornIn("1987-09"), DAY);
    assertThat(met.verdict()).isEqualTo(Verdict.UNKNOWN);
    assertThat(met.reason()).isNull();
    assertThat(met.missing()).isEmpty();
    // 만 40세: 검수 중이어도 불충족 그대로
    assertThat(judge.evaluate(reviewing, bornIn("1986-09"), DAY).verdict())
        .isEqualTo(Verdict.NOT_MET);
  }

  @Test
  void businessAgeYearsSetsTheOpenedRangeFromTheReferenceDay() {
    // 기준일 2026-10-28. 추출의 opened_range와 같아요: 이내는 N년 전 같은 날부터, 미만은 그다음 날부터, 이상은 그날까지, 초과는 그 전날까지
    LocalDate day = LocalDate.of(2026, 10, 28);
    FrameJudge judge =
        new FrameJudge(
            (k, y, p, s) -> OptionalLong.empty(), (d, region, area) -> OptionalLong.empty());
    var within = new Criterion.BusinessAgeYears(meta("within"), 7, Criterion.YearsRule.WITHIN);
    var under = new Criterion.BusinessAgeYears(meta("under"), 3, Criterion.YearsRule.UNDER);
    var atLeast = new Criterion.BusinessAgeYears(meta("at-least"), 3, Criterion.YearsRule.AT_LEAST);
    var over = new Criterion.BusinessAgeYears(meta("over"), 3, Criterion.YearsRule.OVER);

    assertThat(judge.evaluate(within, openedOn("2019-10-28"), day).verdict())
        .isEqualTo(Verdict.MET);
    assertThat(judge.evaluate(within, openedOn("2019-10-27"), day).verdict())
        .isEqualTo(Verdict.NOT_MET);
    assertThat(judge.evaluate(under, openedOn("2023-10-28"), day).verdict())
        .isEqualTo(Verdict.NOT_MET);
    assertThat(judge.evaluate(under, openedOn("2023-10-29"), day).verdict()).isEqualTo(Verdict.MET);
    assertThat(judge.evaluate(atLeast, openedOn("2023-10-28"), day).verdict())
        .isEqualTo(Verdict.MET);
    assertThat(judge.evaluate(atLeast, openedOn("2023-10-29"), day).verdict())
        .isEqualTo(Verdict.NOT_MET);
    assertThat(judge.evaluate(over, openedOn("2023-10-27"), day).verdict()).isEqualTo(Verdict.MET);
    assertThat(judge.evaluate(over, openedOn("2023-10-28"), day).verdict())
        .isEqualTo(Verdict.NOT_MET);

    var met = judge.evaluate(within, openedOn("2024-03-01"), day);
    assertThat(met.criterion().kind()).isEqualTo("BUSINESS_AGE");
    assertThat(met.summary()).isEqualTo("창업 7년 이내 · 개업일 2019-10-28 ~ 2026-10-28 (둘 다 포함)");
    // 사업 정보를 안 넣었으면 사업 이력을 넣어 달라고 해요
    var empty = judge.evaluate(within, withBusiness(business(null, null, null, null)), day);
    assertThat(empty.verdict()).isEqualTo(Verdict.UNKNOWN);
    assertThat(empty.missing()).containsExactly(Input.BUSINESS_HISTORY);
  }

  private static Applicant openedOn(String day) {
    return withBusiness(business(null, null, List.of(record(day, null)), null));
  }

  // ── 공고 단위 ──

  @Test
  void missingInputsComeOnlyFromUndecidedGroups() {
    Criterion.Age youth = new Criterion.Age(meta("youth-age"), 19, 39);
    Criterion.Status merit = new Criterion.Status(meta("merit"), List.of("NATIONAL_MERIT"));
    Frame frame =
        new Frame(
            Field.HOUSING,
            "p",
            1,
            DAY,
            List.of(),
            List.of(
                new Frame.Group("youth", "청년", null, List.of(youth)),
                new Frame.Group("merit", "보훈", null, List.of(merit))),
            List.of(),
            List.of());
    FrameJudge judge =
        new FrameJudge(
            (k, y, p, s) -> OptionalLong.empty(), (d, region, area) -> OptionalLong.empty());
    // 50세라 청년은 불충족 → 보훈 대상군만 남아요
    Applicant old =
        new Applicant(
            LocalDate.of(1976, 1, 1),
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            Map.of());
    FrameJudgment j = judge.judge(frame, old);
    assertThat(j.result()).isEqualTo(Eligibility.NEEDS_INPUT);
    assertThat(j.missingInputs()).containsExactly(Input.STATUSES);

    Applicant merited =
        new Applicant(
            LocalDate.of(1976, 1, 1),
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            Set.of("NATIONAL_MERIT"),
            null,
            Map.of());
    assertThat(judge.judge(frame, merited).missingInputs()).as("지원 가능이면 비어 있어요").isEmpty();
  }
}
