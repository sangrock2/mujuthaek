package kr.mujuthaek.api.eligibility.rule.frame;

import java.time.LocalDate;
import java.time.YearMonth;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 판정에 쓰는 사용자 입력. 세 분야가 같은 입력을 같이 써요. 모두 선택 입력이고, 비어 있는 값이 필요한 조건은 확인 필요가 돼요.
 *
 * <p>저장하거나 로그에 남기지 않아요 (소득·자산·나이·매출).
 *
 * @param birthDate 생년월일 (개인은 본인, 법인은 대표자)
 * @param korean 대한민국 국민이면 true (개인은 본인, 법인은 대표자)
 * @param residenceRegionCode 주민등록 주소의 법정동코드 (시도 2자리, 시군구 5자리, 10자리 모두 받아요)
 * @param residenceMonths 지금 사는 지역에 연속으로 산 개월 수
 * @param childBirthDates 자녀 생년월일. 자녀가 없으면 빈 목록, 답하지 않았으면 null
 * @param expectingChild 임신 중이면 true (태아를 자녀로 세는 조건에 써요)
 * @param statuses 고른 유형 (수급자, 소상공인, 중소기업 …). 고를 게 없으면 빈 집합, 아직 고르지 않았으면 null
 * @param restrictions 고른 신청 제한 사유 (체납, 피후견인 …). 해당 없음이면 빈 집합, 아직 고르지 않았으면 null
 * @param answers 질문(ASK) ID → 답
 * @param birthMonth 출생 연월. 생년월일이 없을 때만 써요 (예전 화면 호환). 그 달 안에서 결과가 갈리면 나이는 확인 필요
 */
public record Applicant(
    LocalDate birthDate,
    Boolean korean,
    String residenceRegionCode,
    Integer residenceMonths,
    MaritalStatus maritalStatus,
    LocalDate marriedOn,
    List<LocalDate> childBirthDates,
    Boolean expectingChild,
    Household household,
    Subscription subscription,
    Business business,
    Set<String> statuses,
    Set<String> restrictions,
    Map<String, Answer> answers,
    YearMonth birthMonth) {

  public Applicant {
    childBirthDates = childBirthDates == null ? null : List.copyOf(childBirthDates);
    household = household == null ? Household.EMPTY : household;
    subscription = subscription == null ? Subscription.EMPTY : subscription;
    business = business == null ? Business.EMPTY : business;
    statuses = statuses == null ? null : Set.copyOf(statuses);
    restrictions = restrictions == null ? null : Set.copyOf(restrictions);
    answers = answers == null ? Map.of() : Map.copyOf(answers);
  }

  /** 출생 연월 없이 (생년월일로만) 만드는 입력. */
  public Applicant(
      LocalDate birthDate,
      Boolean korean,
      String residenceRegionCode,
      Integer residenceMonths,
      MaritalStatus maritalStatus,
      LocalDate marriedOn,
      List<LocalDate> childBirthDates,
      Boolean expectingChild,
      Household household,
      Subscription subscription,
      Business business,
      Set<String> statuses,
      Set<String> restrictions,
      Map<String, Answer> answers) {
    this(
        birthDate,
        korean,
        residenceRegionCode,
        residenceMonths,
        maritalStatus,
        marriedOn,
        childBirthDates,
        expectingChild,
        household,
        subscription,
        business,
        statuses,
        restrictions,
        answers,
        null);
  }

  /** 아무것도 넣지 않은 입력. 이 공고에 무엇이 필요한지 먼저 물어볼 때 써요. */
  public static Applicant empty() {
    return new Applicant(
        null, null, null, null, null, null, null, null, null, null, null, null, null, null);
  }

  /**
   * 세대(가구) 정보.
   *
   * @param size 세대 가구원 수 (태아 포함)
   * @param head 세대주이면 true
   * @param homeless 세대구성원 모두 무주택이면 true
   * @param applicantHomeless 본인이 무주택이면 true. 비어 있고 세대가 무주택이면 본인도 무주택으로 봐요
   * @param homelessYears 무주택 기간 (년)
   * @param monthlyIncomeWon 세대 전체 월평균소득
   * @param applicantMonthlyIncomeWon 본인 월평균소득
   * @param parentsMonthlyIncomeWon 부모 월평균소득 합 (본인 제외)
   * @param applicantAndParentsSize 본인과 부모가 속한 가구원 수 (본인 포함)
   * @param dualIncome 맞벌이면 true
   * @param totalAssetWon 세대 총자산
   * @param applicantTotalAssetWon 본인 총자산
   * @param carValueWon 자동차가액 (없으면 0)
   */
  public record Household(
      Integer size,
      Boolean head,
      Boolean homeless,
      Boolean applicantHomeless,
      Integer homelessYears,
      Long monthlyIncomeWon,
      Long applicantMonthlyIncomeWon,
      Long parentsMonthlyIncomeWon,
      Integer applicantAndParentsSize,
      Boolean dualIncome,
      Long totalAssetWon,
      Long applicantTotalAssetWon,
      Long carValueWon) {

    static final Household EMPTY =
        new Household(null, null, null, null, null, null, null, null, null, null, null, null, null);
  }

  /** 청약통장. 통장이 없으면 months 0. */
  public record Subscription(Integer months, Integer payments, Long balanceWon) {

    static final Subscription EMPTY = new Subscription(null, null, null);
  }

  /**
   * 사업 정보.
   *
   * @param hasSite 사업장이 있으면 true, 없으면 false (모르면 null)
   * @param siteRegionCode 사업장(본점) 소재지의 법정동코드
   * @param history 사업 이력 (대표권이 있는 사업만). 사업이 없으면 빈 목록, 답하지 않았으면 null
   * @param industryCode 지금 하거나 하려는 업종 (한국표준산업분류 11차 5자리)
   * @param revenueByYear 연도 → 그 해 매출액 (판정할 때만 받아요)
   */
  public record Business(
      ApplicantType applicantType,
      Boolean hasSite,
      String siteRegionCode,
      List<BusinessRecord> history,
      String industryCode,
      Map<Integer, Long> revenueByYear) {

    static final Business EMPTY = new Business(null, null, null, null, null, null);

    public Business {
      history = history == null ? null : List.copyOf(history);
      revenueByYear = revenueByYear == null ? null : Map.copyOf(revenueByYear);
    }
  }

  /**
   * 사업 하나.
   *
   * @param openedOn 개업일 (개인은 사업자등록증의 개업연월일, 법인은 설립등기일)
   * @param closedOn 폐업일. 영업 중이면 null
   */
  public record BusinessRecord(LocalDate openedOn, LocalDate closedOn) {}

  public enum MaritalStatus {
    /** 미혼. */
    SINGLE,
    /** 예비신혼부부 (혼인신고 예정, 아직 혼인 전). */
    ENGAGED,
    MARRIED,
    DIVORCED,
    WIDOWED
  }

  public enum ApplicantType {
    INDIVIDUAL,
    CORPORATION
  }
}
