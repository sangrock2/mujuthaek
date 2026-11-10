package kr.mujuthaek.api.eligibility.rule.loan;

import java.time.LocalDate;
import java.util.List;
import kr.mujuthaek.api.eligibility.rule.frame.Applicant.MaritalStatus;

/**
 * 대출 자격을 보는 사용자 입력. 판정 입력(applicant)과 같은 값에 대출용 연소득·순자산·생애최초를 더했어요. 모두 선택 입력이에요.
 *
 * <p>저장하거나 로그에 남기지 않아요.
 *
 * @param childBirthDates 자녀 생년월일. 자녀가 없으면 빈 목록, 답하지 않았으면 null
 * @param householdSize 세대 가구원 수 (단독세대주 구분)
 * @param homeless 세대원 모두 무주택이면 true
 * @param dualIncome 부부 모두 소득이 있으면 true
 * @param annualIncomeWon 부부합산 연소득 (미혼이면 본인)
 * @param applicantAnnualIncomeWon 본인(대출신청인) 연소득
 * @param netAssetWon 부부합산 순자산 (자산 − 부채)
 * @param firstHomePurchase 세대원 모두 집을 산 적이 없어서 생애최초 주택구입이면 true
 */
public record Borrower(
    LocalDate birthDate,
    MaritalStatus maritalStatus,
    LocalDate marriedOn,
    List<LocalDate> childBirthDates,
    Integer householdSize,
    Boolean homeless,
    Boolean dualIncome,
    Long annualIncomeWon,
    Long applicantAnnualIncomeWon,
    Long netAssetWon,
    Boolean firstHomePurchase) {

  public Borrower {
    childBirthDates = childBirthDates == null ? null : List.copyOf(childBirthDates);
  }
}
