package kr.mujuthaek.api.eligibility.rule.frame;

/**
 * 판정에 쓰는 사용자 입력 칸. 값이 없어서 확인 필요가 된 조건은 이 칸을 알려줘요 (화면이 이 칸을 물으면 돼요).
 *
 * <p>field는 요청 JSON의 profile 안 경로예요.
 */
public enum Input {
  BIRTH_DATE("birthDate", "생년월일"),
  KOREAN("korean", "대한민국 국민 여부"),
  RESIDENCE_REGION("residenceRegionCode", "주민등록 주소지"),
  RESIDENCE_MONTHS("residenceMonths", "지금 지역 연속 거주 개월"),
  MARITAL_STATUS("maritalStatus", "혼인 상태"),
  MARRIED_ON("marriedOn", "혼인신고일"),
  CHILD_BIRTH_DATES("childBirthDates", "자녀 생년월일"),
  EXPECTING_CHILD("expectingChild", "임신 여부"),
  HOUSEHOLD_SIZE("household.size", "세대 가구원 수"),
  HOUSEHOLD_HEAD("household.head", "세대주 여부"),
  HOMELESS("household.homeless", "세대 무주택 여부"),
  APPLICANT_HOMELESS("household.applicantHomeless", "본인 무주택 여부"),
  HOMELESS_YEARS("household.homelessYears", "무주택 기간"),
  HOUSEHOLD_INCOME("household.monthlyIncomeWon", "세대 월평균소득"),
  APPLICANT_INCOME("household.applicantMonthlyIncomeWon", "본인 월평균소득"),
  PARENTS_INCOME("household.parentsMonthlyIncomeWon", "부모 월평균소득"),
  APPLICANT_AND_PARENTS_SIZE("household.applicantAndParentsSize", "본인과 부모 가구원 수"),
  DUAL_INCOME("household.dualIncome", "맞벌이 여부"),
  TOTAL_ASSET("household.totalAssetWon", "세대 총자산"),
  APPLICANT_TOTAL_ASSET("household.applicantTotalAssetWon", "본인 총자산"),
  CAR_VALUE("household.carValueWon", "자동차가액"),
  SUBSCRIPTION_MONTHS("subscription.months", "청약통장 가입 개월"),
  SUBSCRIPTION_PAYMENTS("subscription.payments", "청약통장 납입 횟수"),
  SUBSCRIPTION_BALANCE("subscription.balanceWon", "청약통장 예치금"),
  APPLICANT_TYPE("business.applicantType", "신청 형태 (개인·법인)"),
  BUSINESS_SITE("business.siteRegionCode", "사업장 소재지"),
  BUSINESS_HISTORY("business.history", "사업 이력 (개업일·폐업일)"),
  INDUSTRY("business.industryCode", "업종 코드"),
  REVENUE("business.revenueByYear", "연도별 매출액"),
  STATUSES("statuses", "해당 유형"),
  RESTRICTIONS("restrictions", "신청 제한 사유");

  private final String field;
  private final String label;

  Input(String field, String label) {
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
