package kr.mujuthaek.api.eligibility.rule;

/**
 * 기준값 종류 (4-08). 값은 eligibility.base_values 표에 연도별로 넣어요.
 *
 * <p>소득 기준은 가구원 수마다 값이 있고, 자산 기준은 주택 유형(program)마다 값이 있어요.
 */
public enum BaseValueKind {
  /** 기준 중위소득 (보건복지부 고시), 가구원 수별 월 금액. */
  MEDIAN_INCOME,
  /** 도시근로자 가구원수별 가구당 월평균소득 (임대주택 공고가 쓰는 표), 100% 금액. */
  URBAN_WORKER_INCOME,
  /** 도시근로자 가구당 월평균소득 (공공분양·신혼희망타운): 3인 이하는 전체 가구 평균 하나, 4인 이상은 가구원수별 값. */
  URBAN_WORKER_AVERAGE_INCOME,
  /** 총자산가액 상한, 주택 유형별. */
  TOTAL_ASSET,
  /** 자동차가액 상한, 주택 유형별. */
  CAR_VALUE;

  public boolean byHouseholdSize() {
    return this == MEDIAN_INCOME
        || this == URBAN_WORKER_INCOME
        || this == URBAN_WORKER_AVERAGE_INCOME;
  }
}
