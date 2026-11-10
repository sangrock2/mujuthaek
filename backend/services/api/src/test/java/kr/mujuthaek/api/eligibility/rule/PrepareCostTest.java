package kr.mujuthaek.api.eligibility.rule;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import kr.mujuthaek.api.eligibility.rule.PrepareCost.LoanProduct;
import org.junit.jupiter.api.Test;

/** 상품 조건은 테스트용 값이에요 (실제 한도는 관리자가 넣어요). */
class PrepareCostTest {

  private static final LocalDate REF = LocalDate.of(2026, 10, 22);
  private static final LoanProduct YOUTH =
      new LoanProduct(
          "YOUTH",
          "청년 전세자금",
          200_000_000,
          new BigDecimal("0.8"),
          50_000_000L,
          340_000_000L,
          19,
          34,
          List.of());
  private static final LoanProduct GENERAL =
      new LoanProduct(
          "GENERAL",
          "일반 전세자금",
          120_000_000,
          new BigDecimal("0.7"),
          null,
          null,
          null,
          null,
          List.of());

  @Test
  void picksTheLargestLoanTheApplicantQualifiesFor() {
    var a = new ApplicantBuilder().birthMonth(1997, 3).household(1).assets(45_000_000L).build();

    var r =
        PrepareCost.calculate(24_000_000L, a, exactly(32_000_000L), List.of(GENERAL, YOUTH), REF);

    assertThat(r.loan()).isEqualTo(new PrepareCost.Loan("YOUTH", "청년 전세자금", 19_200_000));
    assertThat(r.prepareWon()).isEqualTo(4_800_000);
    assertThat(r.note()).isNull();
  }

  @Test
  void unknownIncomeThatCouldGiveMoreMeansNoAmountYet() {
    var a = new ApplicantBuilder().birthMonth(1997, 3).build();

    var r = PrepareCost.calculate(24_000_000L, a, null, List.of(GENERAL, YOUTH), REF);

    assertThat(r.prepareWon()).isNull();
    assertThat(r.note()).isEqualTo("INCOME_UNKNOWN");
  }

  @Test
  void incomeBandAcrossTheCapIsUnknownNotAGuess() {
    // 연소득 구간 4천만~6천만 원: 청년 상한 5천만 원이 구간 안이라 받을 수 있는지 몰라요
    var a = new ApplicantBuilder().birthMonth(1997, 3).household(1).assets(1L).build();

    var r =
        PrepareCost.calculate(
            24_000_000L,
            a,
            new Bands.Range(40_000_000L, 60_000_000L),
            List.of(GENERAL, YOUTH),
            REF);

    assertThat(r.prepareWon()).isNull();
    assertThat(r.note()).isEqualTo("INCOME_UNKNOWN");
  }

  @Test
  void birthdayMonthAtTheAgeCapSkipsTheProduct() {
    // 기준일 2026-10-22, 1991년 10월생: 만 34세 또는 35세 → 청년(19~34세)은 확실하지 않아서 쓰지 않아요
    var a = new ApplicantBuilder().birthMonth(1991, 10).household(1).assets(1L).build();

    var r = PrepareCost.calculate(24_000_000L, a, exactly(1L), List.of(GENERAL, YOUTH), REF);

    assertThat(r.loan().productCode()).isEqualTo("GENERAL");
  }

  @Test
  void tooOldOrOverTheIncomeLimitFallsBackToTheGeneralLoan() {
    var old = new ApplicantBuilder().birthMonth(1980, 1).build();
    var rich = new ApplicantBuilder().birthMonth(1997, 3).household(1).assets(1L).build();

    var r = PrepareCost.calculate(24_000_000L, old, null, List.of(GENERAL, YOUTH), REF);
    assertThat(r.loan().productCode()).isEqualTo("GENERAL");
    assertThat(r.prepareWon()).isEqualTo(24_000_000 - 16_800_000);
    assertThat(
            PrepareCost.calculate(
                    24_000_000L, rich, exactly(90_000_000L), List.of(GENERAL, YOUTH), REF)
                .loan()
                .productCode())
        .isEqualTo("GENERAL");
  }

  @Test
  void knownIncomeOverTheCapDropsTheProductEvenWhenAssetsAreUnknown() {
    // 소득 9천만 원(청년 상한 5천만 원 초과), 자산은 안 넣음: 청년 대출은 어차피 못 받으니 '자산을 몰라서 판정 불가'가 아니라 일반 대출로 계산
    var a = new ApplicantBuilder().birthMonth(1997, 3).household(1).build();

    var r =
        PrepareCost.calculate(100_000_000L, a, exactly(90_000_000L), List.of(YOUTH, GENERAL), REF);

    assertThat(r.note()).isNull();
    assertThat(r.loan().productCode()).isEqualTo("GENERAL");
    assertThat(r.prepareWon()).isEqualTo(30_000_000);
  }

  /** 정확히 이 연소득 (구간 won-1 초과 ~ won 이하). */
  private static Bands.Range exactly(long won) {
    return new Bands.Range(won - 1, won);
  }

  @Test
  void loanAmountIsExactForRatiosDoubleGetsWrong() {
    // 1000만 × 0.29: double이면 2899999.9999…라 버리면 1원 모자람
    assertThat(PrepareCost.loanAmount(10_000_000L, new BigDecimal("0.29"))).isEqualTo(2_900_000);
    assertThat(PrepareCost.loanAmount(123_456_789L, new BigDecimal("0.575"))).isEqualTo(70_987_653);
  }

  @Test
  void noProductsOrNoPrice() {
    var a = Applicant.empty();
    assertThat(PrepareCost.calculate(10_000_000L, a, null, List.of(), REF).prepareWon())
        .isEqualTo(10_000_000);
    assertThat(PrepareCost.calculate(null, a, null, List.of(GENERAL), REF).note())
        .isEqualTo("PRICE_NOT_ANNOUNCED");
    var newlyweds =
        new LoanProduct(
            "NEWLY",
            "신혼",
            300_000_000,
            new BigDecimal("0.8"),
            null,
            null,
            null,
            null,
            List.of("NEWLYWED"));
    assertThat(PrepareCost.calculate(10_000_000L, a, null, List.of(newlyweds), REF).loan())
        .isNull();
  }
}
