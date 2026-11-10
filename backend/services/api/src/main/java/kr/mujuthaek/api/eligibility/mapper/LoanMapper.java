package kr.mujuthaek.api.eligibility.mapper;

import java.time.LocalDate;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.eligibility.dto.request.JudgmentApplicantRequest;
import kr.mujuthaek.api.eligibility.model.LoanResult;
import kr.mujuthaek.api.eligibility.model.MissingInput;
import kr.mujuthaek.api.eligibility.rule.Eligibility;
import kr.mujuthaek.api.eligibility.rule.frame.Applicant;
import kr.mujuthaek.api.eligibility.rule.loan.Borrower;
import kr.mujuthaek.api.eligibility.rule.loan.LoanJudgment;

/**
 * 판정 입력 → 대출 판정 입력, 상품별 판정 → 정제된 대출 결과 (대출 판정 서비스가 불러요). 잘못된 값은 VALIDATION_FAILED이고, 오류 문장에 입력값을 넣지
 * 않아요.
 */
public final class LoanMapper {

  /** 금액 칸의 상한: 1,000조 원. */
  static final long MAX_WON = 1_000_000_000_000_000L;

  private LoanMapper() {}

  public static Borrower toBorrower(JudgmentApplicantRequest request) {
    Applicant applicant = ApplicantMapper.toApplicant(request, Map.of());
    JudgmentApplicantRequest.LoanRequest loan = request == null ? null : request.loan();
    Long income = loan == null ? null : loan.annualIncomeWon();
    Long mine = loan == null ? null : loan.applicantAnnualIncomeWon();
    Long net = loan == null ? null : loan.netAssetWon();
    if (income != null) {
      checkWon(income, "profile.loan.annualIncomeWon");
    }
    if (mine != null) {
      checkWon(mine, "profile.loan.applicantAnnualIncomeWon");
      check(
          income == null || mine <= income,
          "profile.loan.applicantAnnualIncomeWon",
          "부부합산 연소득보다 클 수 없어요");
    }
    check(
        net == null || (net >= -MAX_WON && net <= MAX_WON),
        "profile.loan.netAssetWon",
        "-1,000조 원 이상 1,000조 원 이하여야 해요");
    Applicant.Household household = applicant.household();
    return new Borrower(
        applicant.birthDate(),
        applicant.maritalStatus(),
        applicant.marriedOn(),
        applicant.childBirthDates(),
        household.size(),
        household.homeless(),
        household.dualIncome(),
        income,
        mine,
        net,
        loan == null ? null : loan.firstHomePurchase());
  }

  /** 정렬을 마친 상품별 판정으로 결과를 만들어요. */
  public static LoanResult toResult(LocalDate asOf, List<LoanJudgment> judgments) {
    return new LoanResult(
        asOf,
        new LoanResult.Counts(
            count(judgments, Eligibility.ELIGIBLE),
            count(judgments, Eligibility.NEEDS_INPUT),
            count(judgments, Eligibility.INELIGIBLE)),
        judgments.stream().map(LoanMapper::item).toList());
  }

  private static LoanResult.Item item(LoanJudgment j) {
    return new LoanResult.Item(
        j.terms().productCode(),
        j.terms().productName(),
        j.terms().loanType(),
        j.status(),
        j.failed(),
        j.status() == Eligibility.INELIGIBLE ? List.of() : j.unclear(),
        j.status() == Eligibility.INELIGIBLE
            ? List.of()
            : j.missing().stream()
                .sorted(Comparator.naturalOrder())
                .map(i -> new MissingInput(i.field(), i.label()))
                .toList(),
        j.terms().limitSummary(),
        j.terms().rateSummary(),
        j.terms().sourceUrl());
  }

  private static int count(List<LoanJudgment> judgments, Eligibility status) {
    return (int) judgments.stream().filter(j -> j.status() == status).count();
  }

  private static void checkWon(long value, String at) {
    check(value >= 0 && value <= MAX_WON, at, "0 이상 1,000조 원 이하여야 해요");
  }

  private static void check(boolean ok, String at, String problem) {
    if (!ok) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, at + ": " + problem);
    }
  }
}
