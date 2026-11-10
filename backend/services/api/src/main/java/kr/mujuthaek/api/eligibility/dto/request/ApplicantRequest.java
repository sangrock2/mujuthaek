package kr.mujuthaek.api.eligibility.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.PastOrPresent;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.PositiveOrZero;
import java.time.LocalDate;
import java.time.YearMonth;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import kr.mujuthaek.api.common.logging.SensitiveFields;
import kr.mujuthaek.api.eligibility.rule.Applicant;
import kr.mujuthaek.api.eligibility.rule.Bands;

/**
 * 판정 요청 본문의 {@code applicant} (API 설계 "판정 입력"). 모든 칸은 비워도 돼요. 형식만 검사하고 값은 어디에도 남기지 않아요.
 *
 * <p>개인정보 기준(2026-10-26)으로 정확한 값 대신 구간을 받아요: 무주택 시작 연월 → 기간 구간, 청약 가입 연월 → 기간 구간, 소득 → 기준 대비 % 구간,
 * 자산·자동차가액 → 금액 구간. 쓸 수 있는 돈은 받지 않아요(준비할 돈과 비교는 화면이 해요).
 *
 * <p>나이는 생년월일로 받아요(2026-11-01). 출생 연월로는 기준일이 생일 달이면 나이가 둘이라 늘 확인 필요였어요. 생년월일도 저장하지 않고 로그에서
 * 가려요({@link SensitiveFields}).
 *
 * @param birthDate 생년월일 ("1997-03-15")
 * @param birthMonth 출생 연월 ("1997-03"). 생년월일이 없을 때만 써요 (예전 화면 호환)
 * @param homelessYears 무주택 기간: LT_1 · 1_3 · 3_5 · 5_PLUS (집이 있으면 homeOwner = true)
 * @param income 본인 월평균소득의 기준 대비 % 구간. 키는 기준 종류 (MEDIAN_INCOME · URBAN_WORKER_INCOME)
 * @param householdIncome 가구 월평균소득의 % 구간. 1인 가구면 비워도 돼요
 * @param incomeYear 소득 % 구간을 계산한 기준 연도 (GET /eligibility/criteria의 year)
 * @param assets 총자산 구간 (GET /eligibility/criteria의 assetCutsWon 사이)
 * @param car 자동차가액 구간 (carCutsWon 사이)
 */
public record ApplicantRequest(
    @PastOrPresent LocalDate birthDate,
    @PastOrPresent YearMonth birthMonth,
    @Pattern(regexp = "[0-9]{5}") String regionCode,
    Boolean householdHead,
    @Min(1) @Max(20) Integer householdSize,
    @Min(0) @Max(20) Integer dependents,
    List<@Pattern(regexp = "UNIVERSITY_STUDENT|JOB_SEEKER|YOUTH|NEWLYWED") String> targetGroups,
    @Pattern(regexp = "SINGLE|MARRIED|ENGAGED") String marital,
    @PastOrPresent YearMonth marriedOn,
    @Min(0) @Max(20) Integer children,
    Boolean homeOwner,
    @Pattern(regexp = "LT_1|1_3|3_5|5_PLUS") String homelessYears,
    @Valid SubscriptionRequest subscription,
    List<@Pattern(regexp = "BASIC_LIVELIHOOD|NEAR_POOR|SINGLE_PARENT") String> welfareStatuses,
    @Schema(
            description = "키: MEDIAN_INCOME · URBAN_WORKER_INCOME",
            example = "{\"MEDIAN_INCOME\": {\"gtPct\": 50, \"lePct\": 100, \"year\": 2026}}")
        Map<@Pattern(regexp = "MEDIAN_INCOME|URBAN_WORKER_INCOME") String, @Valid PercentRange>
            income,
    @Schema(
            description = "키: MEDIAN_INCOME · URBAN_WORKER_INCOME",
            example = "{\"MEDIAN_INCOME\": {\"gtPct\": 50, \"lePct\": 100, \"year\": 2026}}")
        Map<@Pattern(regexp = "MEDIAN_INCOME|URBAN_WORKER_INCOME") String, @Valid PercentRange>
            householdIncome,
    @Min(2000) @Max(2200) Integer incomeYear,
    @Valid WonRange assets,
    @Valid WonRange car,
    List<@Pattern(regexp = "R[23]_[A-Z_]+") String> rankChecks) {

  /**
   * @param months 가입 기간: NONE(통장 없음) · LT_6 · 6_12 · 12_24 · 24_PLUS (개월)
   * @param payments 인정 납입 횟수
   */
  public record SubscriptionRequest(
      @Pattern(regexp = "NONE|LT_6|6_12|12_24|24_PLUS") String months,
      @Min(0) @Max(1000) Integer payments) {}

  /**
   * 기준 대비 % 구간 (gtPct 초과 ~ lePct 이하). 한쪽은 비워도 돼요.
   *
   * @param year 이 구간을 계산한 기준 연도 (criteria의 그 기준 연도). 비우면 incomeYear
   */
  public record PercentRange(
      @Schema(example = "50") @Min(0) @Max(1000) Integer gtPct,
      @Schema(example = "100") @Min(0) @Max(1000) Integer lePct,
      @Min(2000) @Max(2200) Integer year) {

    @AssertTrue(message = "gtPct는 lePct보다 작아야 해요")
    boolean isOrdered() {
      return gtPct == null || lePct == null || gtPct < lePct;
    }

    Bands.Range toRange() {
      return new Bands.Range(
          gtPct == null ? null : gtPct.longValue(), lePct == null ? null : lePct.longValue());
    }
  }

  /** 금액 구간 (gtWon 초과 ~ leWon 이하, 원). 한쪽은 비워도 돼요. */
  public record WonRange(
      @Schema(example = "100000000") @PositiveOrZero Long gtWon,
      @Schema(example = "200000000") @PositiveOrZero Long leWon) {

    @AssertTrue(message = "gtWon은 leWon보다 작아야 해요")
    boolean isOrdered() {
      return gtWon == null || leWon == null || gtWon < leWon;
    }

    Bands.Range toRange() {
      return new Bands.Range(gtWon, leWon);
    }
  }

  public Applicant toApplicant() {
    return new Applicant(
        birthDate,
        birthMonth,
        regionCode,
        householdHead,
        householdSize,
        dependents,
        targetGroups,
        marital,
        marriedOn,
        children,
        homeOwner,
        homelessYears == null ? null : Bands.HOMELESS_YEARS.get(homelessYears),
        subscription == null
            ? null
            : new Applicant.Subscription(
                subscription.months() == null
                    ? null
                    : Bands.SUBSCRIPTION_MONTHS.get(subscription.months()),
                subscription.payments()),
        welfareStatuses,
        ranges(income),
        ranges(householdIncome),
        incomeYear,
        years(income, householdIncome),
        assets == null ? null : assets.toRange(),
        car == null ? null : car.toRange(),
        rankChecks);
  }

  /** 구간마다 적은 기준 연도 (가구 소득 값이 있으면 그쪽이 우선). 없으면 null. */
  private static Map<String, Integer> years(
      Map<String, PercentRange> personal, Map<String, PercentRange> household) {
    Map<String, Integer> out = new LinkedHashMap<>();
    for (var m : java.util.Arrays.asList(personal, household)) {
      if (m != null) {
        m.forEach(
            (k, v) -> {
              if (v != null && v.year() != null) {
                out.put(k, v.year());
              }
            });
      }
    }
    return out.isEmpty() ? null : out;
  }

  private static Map<String, Bands.Range> ranges(Map<String, PercentRange> byStandard) {
    if (byStandard == null) {
      return null;
    }
    Map<String, Bands.Range> out = new LinkedHashMap<>();
    byStandard.forEach((k, v) -> out.put(k, v == null ? null : v.toRange()));
    return out;
  }

  @Override
  public String toString() {
    return SensitiveFields.mask(
        "ApplicantRequest" + toApplicant().toString().substring("Applicant".length()));
  }
}
