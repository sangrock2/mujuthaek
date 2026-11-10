package kr.mujuthaek.api.eligibility.service;

import java.time.Clock;
import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.eligibility.dto.response.CriteriaResponse;
import kr.mujuthaek.api.eligibility.repository.CriteriaStore;
import kr.mujuthaek.api.eligibility.repository.CriteriaStore.CriteriaRow;
import kr.mujuthaek.api.eligibility.repository.LoanProductStore;
import kr.mujuthaek.api.eligibility.rule.IncomeBenchmarks;
import kr.mujuthaek.api.eligibility.rule.PrepareCost.LoanProduct;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** 연도별 판정 기준값. 판정(소득 기준 금액)과 조건 입력 화면이 같이 써요. */
@Service
@Transactional(readOnly = true)
public class CriteriaService {

  private final CriteriaStore store;
  private final LoanProductStore loans;
  private final JsonMapper json;
  private final Clock clock;

  public CriteriaService(
      CriteriaStore store, LoanProductStore loans, JsonMapper json, Clock clock) {
    this.store = store;
    this.loans = loans;
    this.json = json;
    this.clock = clock;
  }

  /**
   * @param year 비우면 오늘 쓰는 가장 최근 연도
   * @param noticeType 공고 유형별 순위 요건이 있으면 그것 (RANK_CRITERIA의 byNoticeType)
   */
  public CriteriaResponse criteria(Integer year, String noticeType) {
    LocalDate today = LocalDate.now(clock);
    int y =
        year != null
            ? year
            : store
                .latestYear(today)
                .or(() -> store.latestBaseYear(today.getYear()))
                .orElseThrow(() -> new CustomException(ErrorCode.CRITERIA_NOT_FOUND));
    Optional<CriteriaRow> ranks = store.find("RANK_CRITERIA", y);
    Map<String, Long> median = monthlyIncome("MEDIAN_INCOME", y);
    // 도시근로자 소득은 보통 전해 값이 마지막이라, 그해 값이 없으면 가장 가까운 앞 해 값을 줘요 (urbanWorkerIncomeYear)
    int urbanYear = y;
    Map<String, Long> urban = monthlyIncome("URBAN_WORKER_INCOME", y);
    for (int back = 1; urban.isEmpty() && back <= 2; back++) {
      urbanYear = y - back;
      urban = monthlyIncome("URBAN_WORKER_INCOME", urbanYear);
    }
    if (median.isEmpty() && urban.isEmpty() && ranks.isEmpty()) {
      throw new CustomException(ErrorCode.CRITERIA_NOT_FOUND);
    }
    LocalDate validFrom =
        store
            .find("MEDIAN_INCOME", y)
            .or(() -> ranks)
            .map(CriteriaRow::validFrom)
            .orElse(LocalDate.of(y, 1, 1));
    return new CriteriaResponse(
        y,
        validFrom,
        nullIfEmpty(median),
        nullIfEmpty(urban),
        urban.isEmpty() ? null : urbanYear,
        ranks.map(r -> rankCriteria(json.readTree(r.data()), noticeType)).orElse(null),
        cuts(
            store.assetCuts("TOTAL_ASSET", y),
            loans.enabled().stream().map(LoanProduct::maxTotalAssetsWon)),
        cuts(store.assetCuts("CAR_VALUE", y), java.util.stream.Stream.empty()));
  }

  /**
   * 가구원 수별 월 금액 (판정의 소득 기준). 관리자가 넣은 값(criteria_sets)을 먼저, 없으면 고시 값(base_values)을 써요. 그해 값이 없으면 빈
   * 값.
   */
  public Map<String, Long> monthlyIncome(String kind, int year) {
    Map<String, Long> set =
        store.find(kind, year).map(r -> monthly(json.readTree(r.data()))).orElse(Map.of());
    if (!set.isEmpty()) {
      return set;
    }
    // 도시근로자 소득은 가구원수별(URBAN_WORKER_INCOME)과 가구당 평균(URBAN_WORKER_AVERAGE_INCOME, 공공분양)이 다른 표예요
    return store.baseIncome(List.of(kind), year);
  }

  private static Map<String, Long> nullIfEmpty(Map<String, Long> m) {
    return m.isEmpty() ? null : m;
  }

  /** 구간 경계: 기준표 금액 + 대출 상품 상한, 겹치지 않게 작은 순. */
  private static List<Long> cuts(List<Long> base, java.util.stream.Stream<Long> more) {
    return java.util.stream.Stream.concat(base.stream(), more)
        .filter(java.util.Objects::nonNull)
        .distinct()
        .sorted()
        .toList();
  }

  /**
   * 판정 엔진에 넘길 기준 소득 월액. 기준 중위소득은 MEDIAN_INCOME, 도시근로자 가구원수별은 URBAN_WORKER_INCOME, 가구당 평균(공공분양)은
   * URBAN_WORKER_AVERAGE_INCOME 값을 써요(없으면 가구원수별). 한 번의 판정 안에서 같은 연도를 여러 번 읽지 않게 기억해 둬요.
   */
  public IncomeBenchmarks benchmarks() {
    Map<String, Map<String, Long>> cache = new java.util.HashMap<>();
    return (standard, year, householdSize) -> {
      String kind =
          "MEDIAN_INCOME".equals(standard) || "URBAN_WORKER_AVERAGE_INCOME".equals(standard)
              ? standard
              : "URBAN_WORKER_INCOME";
      Map<String, Long> table = cache.computeIfAbsent(kind + year, k -> monthlyIncome(kind, year));
      // 가구당 평균 표가 없으면(관리자 표 등) 가구원수별 표로
      if (table.isEmpty() && "URBAN_WORKER_AVERAGE_INCOME".equals(kind)) {
        table =
            cache.computeIfAbsent(
                "URBAN_WORKER_INCOME" + year, k -> monthlyIncome("URBAN_WORKER_INCOME", year));
      }
      return table.get(String.valueOf(householdSize));
    };
  }

  private static Map<String, Long> monthly(JsonNode data) {
    Map<String, Long> out = new LinkedHashMap<>();
    data.path("monthlyWon").properties().forEach(e -> out.put(e.getKey(), e.getValue().asLong()));
    return out;
  }

  private static JsonNode rankCriteria(JsonNode data, String noticeType) {
    JsonNode byType = data.path("byNoticeType").path(noticeType == null ? "" : noticeType);
    return byType.isMissingNode() ? data.path("ranks") : byType;
  }
}
