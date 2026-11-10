package kr.mujuthaek.api.eligibility.rule;

import java.time.LocalDate;
import java.time.YearMonth;
import java.util.List;
import java.util.Map;
import kr.mujuthaek.api.common.logging.SensitiveFields;
import kr.mujuthaek.api.eligibility.rule.Bands.Range;
import kr.mujuthaek.api.eligibility.rule.Bands.Span;

/**
 * 판정에 넣는 사용자 입력 (API 설계 "판정 입력"). 모든 칸은 비워도 되고(null), 비운 조건은 "확인 필요"로 판정해요.
 *
 * <p>나이는 생년월일로, 기간·소득·자산은 정확한 값 대신 구간({@link Bands})으로 받아요. 서버는 이 값을 저장하지 않고 로그에도 남기지 않아요.
 * toString은 생년월일과 구간도 가려요.
 *
 * @param birthDate 생년월일. 있으면 이걸로 만 나이를 정확히 계산해요
 * @param birthMonth 출생 연월. 생년월일이 없을 때만 써요 (예전 화면 호환). 기준일이 생일 달이면 나이가 둘이라 확인 필요
 * @param regionCode 지금 사는 시군구 5자리
 * @param householdSize 세대원 수 (나 포함)
 * @param dependents 부양가족 수 (나 제외)
 * @param targetGroups 지금 상황 (UNIVERSITY_STUDENT, JOB_SEEKER, YOUTH, NEWLYWED)
 * @param marital SINGLE · MARRIED · ENGAGED
 * @param marriedOn 혼인신고 연월
 * @param homeOwner 집이 있으면 true
 * @param homelessYears 무주택 기간 구간 (년)
 * @param welfareStatuses BASIC_LIVELIHOOD 수급자 · NEAR_POOR 차상위 · SINGLE_PARENT 한부모
 * @param personalIncome 본인 월평균소득의 기준 대비 % 구간 (기준 종류 MEDIAN_INCOME · URBAN_WORKER_INCOME마다)
 * @param householdIncome 가구 월평균소득의 % 구간. 1인 가구면 비워도 본인 값을 써요
 * @param incomeYear 소득 % 구간을 계산한 기준 연도 (GET /eligibility/criteria의 year). 비우면 공고 기준 연도와 같다고 봐요
 * @param incomeYears 기준 종류마다 다른 연도로 계산했을 때 (도시근로자 소득은 보통 전해 값). 없으면 incomeYear
 * @param assets 총자산 구간 (원)
 * @param car 자동차가액 구간 (원)
 * @param rankChecks 2·3순위 자기 확인 체크 키 (GET /eligibility/criteria가 줘요)
 */
public record Applicant(
    LocalDate birthDate,
    YearMonth birthMonth,
    String regionCode,
    Boolean householdHead,
    Integer householdSize,
    Integer dependents,
    List<String> targetGroups,
    String marital,
    YearMonth marriedOn,
    Integer children,
    Boolean homeOwner,
    Span homelessYears,
    Subscription subscription,
    List<String> welfareStatuses,
    Map<String, Range> personalIncome,
    Map<String, Range> householdIncome,
    Integer incomeYear,
    Map<String, Integer> incomeYears,
    Range assets,
    Range car,
    List<String> rankChecks) {

  /** 청약통장 가입 기간 구간(개월)과 인정 납입 횟수. */
  public record Subscription(Span months, Integer payments) {}

  public static Applicant empty() {
    return new Applicant(
        null, null, null, null, null, null, null, null, null, null, null, null, null, null, null,
        null, null, null, null, null, null);
  }

  /** 기준일의 만 나이 범위 [어릴 때, 많을 때]. 생년월일이 있으면 두 값이 같고, 출생 연월만 있으면 기준일이 생일 달일 때 달라요. 둘 다 없으면 null. */
  public int[] ages(LocalDate referenceDate) {
    if (birthDate != null) {
      int age = Periods.age(birthDate, referenceDate);
      return new int[] {age, age};
    }
    return birthMonth == null ? null : Bands.ages(birthMonth, referenceDate);
  }

  /** 이 기준 종류의 % 구간을 계산한 연도. 모르면 null. */
  public Integer incomeYearOf(String standard) {
    Integer own = incomeYears == null ? null : incomeYears.get(standard);
    return own != null ? own : incomeYear;
  }

  /** 가구 소득 % 구간. 1인 가구면 가구 = 본인이라 본인 값으로 채워요. */
  public Map<String, Range> householdIncomeOrSelf() {
    if (householdIncome != null) {
      return householdIncome;
    }
    return Integer.valueOf(1).equals(householdSize) ? personalIncome : null;
  }

  @Override
  public String toString() {
    return SensitiveFields.mask(
        "Applicant[birthDate="
            + birthDate
            + ", birthMonth="
            + birthMonth
            + ", regionCode="
            + regionCode
            + ", householdHead="
            + householdHead
            + ", householdSize="
            + householdSize
            + ", dependents="
            + dependents
            + ", targetGroups="
            + targetGroups
            + ", marital="
            + marital
            + ", marriedOn="
            + marriedOn
            + ", children="
            + children
            + ", homeOwner="
            + homeOwner
            + ", homelessYears="
            + homelessYears
            + ", subscription="
            + subscription
            + ", welfareStatuses="
            + welfareStatuses
            + ", personalIncome="
            + personalIncome
            + ", householdIncome="
            + householdIncome
            + ", incomeYear="
            + incomeYear
            + ", incomeYears="
            + incomeYears
            + ", assets="
            + assets
            + ", car="
            + car
            + ", rankChecks="
            + rankChecks
            + "]");
  }
}
