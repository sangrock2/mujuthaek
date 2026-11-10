package kr.mujuthaek.api.eligibility.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDate;
import java.time.YearMonth;
import java.util.List;
import java.util.Map;
import kr.mujuthaek.api.eligibility.rule.frame.Applicant.ApplicantType;
import kr.mujuthaek.api.eligibility.rule.frame.Applicant.MaritalStatus;

/**
 * 사용자 입력 (세 분야 같이 써요). 모두 선택 입력이에요. 칸 뜻은 rule/frame/Applicant를 봐요.
 *
 * <p>나이는 birthDate(생년월일)로 판정해요. birthMonth(출생 연월, 예: 1997-03)는 생년월일이 없을 때만 써요 (예전 화면 호환).
 *
 * <p>저장하거나 로그에 남기지 않아요. 잘못된 값이 와도 오류 메시지에 그 값을 넣지 않아요.
 *
 * <p>판정 엔진(rule/frame)용 입력이에요. 공고 판정 API의 입력은 API 문서 모양의 {@link ApplicantRequest}이고, 둘을 하나로 합치는 건
 * 따로 해요 (.docs/eligibility_compare.md).
 */
public record JudgmentApplicantRequest(
    LocalDate birthDate,
    Boolean korean,
    @Schema(
            description = "법정동코드 2·5·8·10자리",
            pattern = "^(\\d{2}|\\d{5}|\\d{8}|\\d{10})$",
            example = "1165000000")
        String residenceRegionCode,
    Integer residenceMonths,
    MaritalStatus maritalStatus,
    LocalDate marriedOn,
    List<LocalDate> childBirthDates,
    Boolean expectingChild,
    HouseholdRequest household,
    SubscriptionRequest subscription,
    BusinessRequest business,
    List<String> statuses,
    List<String> restrictions,
    LoanRequest loan,
    YearMonth birthMonth) {

  public record HouseholdRequest(
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
      Long carValueWon) {}

  public record SubscriptionRequest(Integer months, Integer payments, Long balanceWon) {}

  public record BusinessRequest(
      ApplicantType applicantType,
      Boolean hasSite,
      @Schema(
              description = "법정동코드 2·5·8·10자리",
              pattern = "^(\\d{2}|\\d{5}|\\d{8}|\\d{10})$",
              example = "1165000000")
          String siteRegionCode,
      List<BusinessRecordRequest> history,
      @Schema(description = "업종 코드 5자리", pattern = "^\\d{5}$", example = "47190")
          String industryCode,
      @Schema(description = "연도별 매출(원)", example = "{\"2025\": 120000000}")
          Map<Integer, Long> revenueByYear) {}

  public record BusinessRecordRequest(LocalDate openedOn, LocalDate closedOn) {}

  /**
   * 대출용 소득·자산·생애최초 (대출 자격 판정에만 써요). 주택도시기금 상품안내 기준이라 판정의 월소득·총자산과 따로 받아요.
   *
   * @param annualIncomeWon 부부합산 연소득 (미혼이면 본인)
   * @param applicantAnnualIncomeWon 본인(대출신청인) 연소득
   * @param netAssetWon 부부합산 순자산 (자산 − 부채, 음수일 수 있어요)
   * @param firstHomePurchase 세대원 모두 집을 산 적이 없어서 생애최초 주택구입이면 true (구입 대출에 써요)
   */
  public record LoanRequest(
      Long annualIncomeWon,
      Long applicantAnnualIncomeWon,
      Long netAssetWon,
      Boolean firstHomePurchase) {}
}
