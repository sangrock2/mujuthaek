package kr.mujuthaek.api.eligibility.rule.loan;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.util.List;
import kr.mujuthaek.api.eligibility.MigrationLoanCatalog;
import kr.mujuthaek.api.eligibility.rule.Eligibility;
import kr.mujuthaek.api.eligibility.rule.frame.Applicant.MaritalStatus;
import org.junit.jupiter.api.Test;

/** 대출 자격 판정: 마이그레이션에 넣은 실제 상품 조건으로 가능·확인 필요·불가와 이유를 봐요. 기준일은 2026-10-21. */
class LoanCheckTest {

  private static final LocalDate DAY = LocalDate.parse("2026-10-21");
  private static final MigrationLoanCatalog CATALOG = MigrationLoanCatalog.load();

  private static LoanTerms terms(String code, LocalDate day) {
    return CATALOG.asOf(day).stream()
        .filter(t -> t.productCode().equals(code))
        .findFirst()
        .orElseThrow();
  }

  private static LoanJudgment judge(String code, Borrower b) {
    return LoanCheck.check(terms(code, DAY), b, DAY);
  }

  /** 1999-05-05생(만 27세) 미혼 1인 세대, 무주택, 연소득 4천만 원, 순자산 1억 원, 자녀 없음. */
  private static Borrower youth() {
    return new Borrower(
        LocalDate.parse("1999-05-05"),
        MaritalStatus.SINGLE,
        null,
        List.of(),
        1,
        true,
        false,
        40_000_000L,
        40_000_000L,
        100_000_000L,
        true);
  }

  private static Borrower with(
      Borrower b, LocalDate birth, MaritalStatus status, LocalDate marriedOn, Integer size) {
    return new Borrower(
        birth,
        status,
        marriedOn,
        b.childBirthDates(),
        size,
        b.homeless(),
        b.dualIncome(),
        b.annualIncomeWon(),
        b.applicantAnnualIncomeWon(),
        b.netAssetWon(),
        b.firstHomePurchase());
  }

  private static Borrower money(Borrower b, Long couple, Long mine, Long net) {
    return new Borrower(
        b.birthDate(),
        b.maritalStatus(),
        b.marriedOn(),
        b.childBirthDates(),
        b.householdSize(),
        b.homeless(),
        b.dualIncome(),
        couple,
        mine,
        net,
        b.firstHomePurchase());
  }

  private static Borrower family(Borrower b, List<LocalDate> children, Boolean firstHome) {
    return new Borrower(
        b.birthDate(),
        b.maritalStatus(),
        b.marriedOn(),
        children,
        b.householdSize(),
        b.homeless(),
        b.dualIncome(),
        b.annualIncomeWon(),
        b.applicantAnnualIncomeWon(),
        b.netAssetWon(),
        firstHome);
  }

  @Test
  void youngSingleRenterCanTakeTheYouthLoans() {
    assertThat(judge("BEOTIMMOK_YOUTH", youth()).status()).isEqualTo(Eligibility.ELIGIBLE);
    assertThat(judge("YOUTH_MONTHLY_RENT", youth()).status()).isEqualTo(Eligibility.ELIGIBLE);
    assertThat(judge("BEOTIMMOK_GENERAL", youth()).status()).isEqualTo(Eligibility.ELIGIBLE);
    assertThat(judge("HOUSING_STABILITY_MONTHLY_RENT", youth()).status())
        .isEqualTo(Eligibility.ELIGIBLE);
  }

  @Test
  void ageOutsideTheRangeIsNotEligibleWithTheReason() {
    // 1991-10-21생은 기준일에 만 35세
    LoanJudgment j =
        judge(
            "BEOTIMMOK_YOUTH",
            with(youth(), LocalDate.parse("1991-10-21"), MaritalStatus.SINGLE, null, 1));
    assertThat(j.status()).isEqualTo(Eligibility.INELIGIBLE);
    assertThat(j.failed()).containsExactly("나이가 만 19~34세여야 해요");
    // 하루 늦게 태어나면 만 34세라 충족
    assertThat(
            judge(
                    "BEOTIMMOK_YOUTH",
                    with(youth(), LocalDate.parse("1991-10-22"), MaritalStatus.SINGLE, null, 1))
                .status())
        .isEqualTo(Eligibility.ELIGIBLE);
  }

  @Test
  void incomeAboveTheCapFailsUnlessAnExceptionApplies() {
    LoanJudgment single = judge("BEOTIMMOK_YOUTH", money(youth(), 65_432_100L, null, 100_000_000L));
    assertThat(single.status()).isEqualTo(Eligibility.INELIGIBLE);
    assertThat(single.failed())
        .containsExactly("부부합산 연소득이 5,000만 원 이하여야 해요 (신혼가구 7,500만 원, 2자녀 이상 6,000만 원 이하면 가능)");
    // 사용자가 넣은 금액은 이유 문장에 넣지 않아요
    assertThat(String.join(" ", single.failed()))
        .doesNotContain("6,543")
        .doesNotContain("65432100");

    Borrower newlywed =
        with(
            money(youth(), 70_000_000L, null, 100_000_000L),
            LocalDate.parse("1996-01-01"),
            MaritalStatus.MARRIED,
            LocalDate.parse("2024-03-01"),
            2);
    assertThat(judge("BEOTIMMOK_YOUTH", newlywed).status()).isEqualTo(Eligibility.ELIGIBLE);
  }

  @Test
  void missingIncomeAsksForIt() {
    LoanJudgment j = judge("BEOTIMMOK_YOUTH", money(youth(), null, null, 100_000_000L));
    assertThat(j.status()).isEqualTo(Eligibility.NEEDS_INPUT);
    assertThat(j.missing()).containsExactly(LoanInput.ANNUAL_INCOME);
    assertThat(j.unclear()).containsExactly("부부합산 연소득이 있어야 소득 조건을 볼 수 있어요");
  }

  @Test
  void monthlyRentYouthLoanNeedsASingleHousehold() {
    LoanJudgment j =
        judge(
            "YOUTH_MONTHLY_RENT",
            with(youth(), youth().birthDate(), MaritalStatus.SINGLE, null, 2));
    assertThat(j.status()).isEqualTo(Eligibility.INELIGIBLE);
    assertThat(j.failed()).containsExactly("단독세대주(1인 세대)여야 해요");
  }

  @Test
  void newlywedJeonseAcceptsOneEarnerFromOctober19() {
    Borrower couple =
        with(
            money(youth(), 90_000_000L, 45_000_000L, 200_000_000L),
            LocalDate.parse("1995-01-01"),
            MaritalStatus.MARRIED,
            LocalDate.parse("2023-05-01"),
            2);
    assertThat(judge("BEOTIMMOK_NEWLYWED", couple).status()).isEqualTo(Eligibility.ELIGIBLE);
    LocalDate before = LocalDate.parse("2026-10-18");
    assertThat(LoanCheck.check(terms("BEOTIMMOK_NEWLYWED", before), couple, before).status())
        .isEqualTo(Eligibility.INELIGIBLE);

    LoanJudgment single = judge("BEOTIMMOK_NEWLYWED", youth());
    assertThat(single.status()).isEqualTo(Eligibility.INELIGIBLE);
    assertThat(single.failed()).containsExactly("혼인 7년 이내 신혼부부(또는 3개월 안 결혼 예정)여야 해요");
  }

  @Test
  void didimdolExcludesSingleHouseholdersUnder30() {
    // 만 27세 미혼 1인 세대 → 제외
    LoanJudgment alone = judge("DIDIMDOL", youth());
    assertThat(alone.status()).isEqualTo(Eligibility.INELIGIBLE);
    assertThat(alone.failed()).containsExactly("만 30세 미만 미혼 단독세대주는 받을 수 없어요");
    // 부모와 같이 사는 세대면 부양 기간에 달려서 확인 필요 (물을 칸이 없어요)
    LoanJudgment withParents =
        judge("DIDIMDOL", with(youth(), youth().birthDate(), MaritalStatus.SINGLE, null, 3));
    assertThat(withParents.status()).isEqualTo(Eligibility.NEEDS_INPUT);
    assertThat(withParents.missing()).isEmpty();
    assertThat(withParents.unclear())
        .containsExactly("만 30세 미만 미혼세대주는 부모나 미성년 형제자매를 6개월 이상 부양한 세대여야 해요");
    // 만 30세 이상이면 상관없어요
    assertThat(
            judge(
                    "DIDIMDOL",
                    with(youth(), LocalDate.parse("1990-01-01"), MaritalStatus.SINGLE, null, 1))
                .status())
        .isEqualTo(Eligibility.ELIGIBLE);
  }

  @Test
  void firstHomeRaisesTheDidimdolIncomeCap() {
    Borrower over =
        with(
            money(youth(), 65_000_000L, 65_000_000L, 100_000_000L),
            LocalDate.parse("1990-01-01"),
            MaritalStatus.SINGLE,
            null,
            1);
    LoanJudgment unknown = judge("DIDIMDOL", family(over, List.of(), null));
    assertThat(unknown.status()).isEqualTo(Eligibility.NEEDS_INPUT);
    assertThat(unknown.missing()).containsExactly(LoanInput.FIRST_HOME_PURCHASE);
    assertThat(judge("DIDIMDOL", family(over, List.of(), true)).status())
        .isEqualTo(Eligibility.ELIGIBLE);
    assertThat(judge("DIDIMDOL", family(over, List.of(), false)).status())
        .isEqualTo(Eligibility.INELIGIBLE);
  }

  @Test
  void newlywedPurchaseNeedsAFirstHome() {
    Borrower couple =
        with(
            youth(),
            LocalDate.parse("1995-01-01"),
            MaritalStatus.MARRIED,
            LocalDate.parse("2023-05-01"),
            2);
    LoanJudgment j = judge("DIDIMDOL_NEWLYWED", family(couple, List.of(), false));
    assertThat(j.status()).isEqualTo(Eligibility.INELIGIBLE);
    assertThat(j.failed()).containsExactly("생애최초 주택구입(세대원 모두 집을 산 적이 없음)이어야 해요");
    assertThat(judge("DIDIMDOL_NEWLYWED", family(couple, List.of(), true)).status())
        .isEqualTo(Eligibility.ELIGIBLE);
  }

  @Test
  void newbornLoansCountChildrenBornWithinTwoYearsSince2023() {
    Borrower parents =
        with(
            money(youth(), 100_000_000L, 60_000_000L, 300_000_000L),
            LocalDate.parse("1992-01-01"),
            MaritalStatus.MARRIED,
            LocalDate.parse("2020-01-01"),
            3);
    assertThat(
            judge("DIDIMDOL_NEWBORN", family(parents, List.of(LocalDate.parse("2025-06-01")), true))
                .status())
        .isEqualTo(Eligibility.ELIGIBLE);
    LoanJudgment old =
        judge("BEOTIMMOK_NEWBORN", family(parents, List.of(LocalDate.parse("2024-10-20")), true));
    assertThat(old.status()).isEqualTo(Eligibility.INELIGIBLE);
    assertThat(old.failed()).containsExactly("기준일 전 2년 안에 낳은 자녀가 있어야 해요 (2023년 이후 출생)");
    LoanJudgment unknown = judge("BEOTIMMOK_NEWBORN", family(parents, null, true));
    assertThat(unknown.status()).isEqualTo(Eligibility.NEEDS_INPUT);
    assertThat(unknown.missing()).containsExactly(LoanInput.CHILD_BIRTH_DATES);
  }

  @Test
  void youthDreamLoanIsAtMostNeedsCheck() {
    LoanJudgment j =
        judge(
            "DIDIMDOL_YOUTH_DREAM",
            with(youth(), LocalDate.parse("1990-01-01"), MaritalStatus.SINGLE, null, 1));
    assertThat(j.status()).isEqualTo(Eligibility.NEEDS_INPUT);
    assertThat(j.missing()).isEmpty();
    assertThat(j.unclear()).singleElement().asString().contains("청년 주택드림 통장으로 청약에 당첨");
  }

  @Test
  void netAssetCapsDifferBetweenRentAndPurchase() {
    Borrower rich =
        with(
            money(youth(), 40_000_000L, 40_000_000L, 400_000_000L),
            LocalDate.parse("1990-01-01"),
            MaritalStatus.SINGLE,
            null,
            1);
    LoanJudgment rent = judge("BEOTIMMOK_GENERAL", rich);
    assertThat(rent.status()).isEqualTo(Eligibility.INELIGIBLE);
    assertThat(rent.failed()).containsExactly("부부합산 순자산이 3억 4,500만 원 이하여야 해요");
    assertThat(judge("DIDIMDOL", rich).status()).isEqualTo(Eligibility.ELIGIBLE);
  }

  @Test
  void owningAHomeRulesOutEveryProduct() {
    Borrower owner =
        new Borrower(
            youth().birthDate(),
            MaritalStatus.SINGLE,
            null,
            List.of(),
            1,
            false,
            false,
            40_000_000L,
            40_000_000L,
            100_000_000L,
            true);
    for (LoanTerms t : CATALOG.asOf(DAY)) {
      LoanJudgment j = LoanCheck.check(t, owner, DAY);
      assertThat(j.status()).as(t.productCode()).isEqualTo(Eligibility.INELIGIBLE);
      assertThat(j.failed()).as(t.productCode()).contains("세대원 모두 무주택이어야 해요");
    }
  }

  @Test
  void emptyInputNeverSaysEligible() {
    Borrower nothing =
        new Borrower(null, null, null, null, null, null, null, null, null, null, null);
    for (LoanTerms t : CATALOG.asOf(DAY)) {
      LoanJudgment j = LoanCheck.check(t, nothing, DAY);
      assertThat(j.status()).as(t.productCode()).isEqualTo(Eligibility.NEEDS_INPUT);
      assertThat(j.missing())
          .as(t.productCode())
          .contains(LoanInput.HOMELESS, LoanInput.ANNUAL_INCOME, LoanInput.NET_ASSET);
    }
  }

  @Test
  void catalogHasTenProductsOnTheDay() {
    assertThat(CATALOG.asOf(DAY))
        .extracting(LoanTerms::productCode)
        .containsExactly(
            "BEOTIMMOK_GENERAL",
            "BEOTIMMOK_YOUTH",
            "BEOTIMMOK_NEWLYWED",
            "BEOTIMMOK_NEWBORN",
            "YOUTH_MONTHLY_RENT",
            "HOUSING_STABILITY_MONTHLY_RENT",
            "DIDIMDOL",
            "DIDIMDOL_NEWLYWED",
            "DIDIMDOL_NEWBORN",
            "DIDIMDOL_YOUTH_DREAM");
    assertThat(CATALOG.asOf(LocalDate.parse("2025-12-31"))).isEmpty();
  }
}
