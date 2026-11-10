package kr.mujuthaek.api.eligibility.rule.loan;

/**
 * 대출 자격 판정에 쓰는 사용자 입력 칸. 값이 없어서 결과가 정해지지 않으면 결과(LoanResult)의 missingInputs로 알려 줘요.
 *
 * <p>field는 공고 판정의 Input과 같이 JudgmentApplicantRequest 안의 칸 경로예요 (예: loan.annualIncomeWon).
 */
public enum LoanInput {
  BIRTH_DATE("birthDate", "생년월일"),
  MARITAL_STATUS("maritalStatus", "혼인 상태"),
  MARRIED_ON("marriedOn", "혼인신고일"),
  CHILD_BIRTH_DATES("childBirthDates", "자녀 생년월일"),
  HOUSEHOLD_SIZE("household.size", "세대 가구원 수"),
  HOMELESS("household.homeless", "세대원 모두 무주택인지"),
  DUAL_INCOME("household.dualIncome", "맞벌이 여부"),
  ANNUAL_INCOME("loan.annualIncomeWon", "부부합산 연소득"),
  APPLICANT_ANNUAL_INCOME("loan.applicantAnnualIncomeWon", "본인 연소득"),
  NET_ASSET("loan.netAssetWon", "부부합산 순자산"),
  FIRST_HOME_PURCHASE("loan.firstHomePurchase", "생애최초 주택구입인지");

  private final String field;
  private final String label;

  LoanInput(String field, String label) {
    this.field = field;
    this.label = label;
  }

  public String field() {
    return field;
  }

  public String label() {
    return label;
  }
}
