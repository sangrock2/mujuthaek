package kr.mujuthaek.api.eligibility.dto.response;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import tools.jackson.databind.JsonNode;

/**
 * 판정 기준 금액 (GET /eligibility/criteria). 조건 입력 화면의 "총자산가액 34,500만 원 이하" 같은 문구에 써요.
 *
 * <p>판정 입력의 구간 값도 이 값으로 계산해요: 소득 % 구간 = 월평균소득 ÷ 가구원 수별 기준 월액, 자산·자동차가액 구간 = 아래 경계 금액 사이.
 *
 * @param year 기준 연도. 판정 입력의 incomeYear로 그대로 보내요
 * @param medianIncomeMonthlyWon 가구원 수("1"·"2" …)별 기준 중위소득 월액. 그해 값이 없으면 null
 * @param urbanWorkerIncomeMonthlyWon 가구원 수별 도시근로자 가구당 월평균소득. 그해 값이 없으면 가장 가까운 앞 해(2년까지) 값
 * @param urbanWorkerIncomeYear urbanWorkerIncomeMonthlyWon의 연도. 소득 % 구간의 year로 보내요
 * @param rankCriteria 순위 요건 [{ rank, rule(ANY·ALL), items: [{ key, label, … }] }]. 그해 값이 없으면 null
 * @param assetCutsWon 총자산 구간 경계 (주택 유형별 상한·대출 상한, 작은 순)
 * @param carCutsWon 자동차가액 구간 경계 (작은 순)
 */
public record CriteriaResponse(
    int year,
    LocalDate validFrom,
    Map<String, Long> medianIncomeMonthlyWon,
    Map<String, Long> urbanWorkerIncomeMonthlyWon,
    Integer urbanWorkerIncomeYear,
    JsonNode rankCriteria,
    List<Long> assetCutsWon,
    List<Long> carCutsWon) {}
