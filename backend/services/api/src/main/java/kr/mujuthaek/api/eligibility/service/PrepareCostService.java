package kr.mujuthaek.api.eligibility.service;

import java.time.Clock;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import kr.mujuthaek.api.eligibility.repository.LoanProductStore;
import kr.mujuthaek.api.eligibility.rule.Applicant;
import kr.mujuthaek.api.eligibility.rule.Bands;
import kr.mujuthaek.api.eligibility.rule.IncomeBenchmarks;
import kr.mujuthaek.api.eligibility.rule.PrepareCost;
import org.springframework.stereotype.Service;

/** 보증금으로 준비할 돈 (받을 수 있는 대출을 뺀 금액). 입력은 저장하지 않아요. */
@Service
public class PrepareCostService {

  private final LoanProductStore products;
  private final CriteriaService criteria;
  private final Clock clock;

  public PrepareCostService(LoanProductStore products, CriteriaService criteria, Clock clock) {
    this.products = products;
    this.criteria = criteria;
    this.clock = clock;
  }

  public PrepareCost.Result prepare(Long depositWon, Applicant applicant) {
    return preparer(applicant).apply(depositWon);
  }

  /** 같은 판정 안에서 주택형마다 상품을 다시 읽지 않게, 상품 목록을 한 번 읽어 계산하는 함수를 줘요. */
  public Function<Long, PrepareCost.Result> preparer(Applicant applicant) {
    List<PrepareCost.LoanProduct> loaded = products.enabled();
    LocalDate today = LocalDate.now(clock);
    Bands.Range income = annualIncomeWon(applicant, criteria.benchmarks(), today);
    return deposit -> PrepareCost.calculate(deposit, applicant, income, loaded, today);
  }

  /** 대출 상품의 연소득 상한과 비교할 가구 연소득 금액 구간: 소득 % 구간 × 그 기준 연도 기준 월액 × 12. 기준 중위소득 구간을 먼저 써요. 모르면 null. */
  static Bands.Range annualIncomeWon(Applicant a, IncomeBenchmarks benchmarks, LocalDate today) {
    Map<String, Bands.Range> bands = a.householdIncomeOrSelf();
    if (bands == null || a.householdSize() == null) {
      return null;
    }
    for (String key : List.of("MEDIAN_INCOME", "URBAN_WORKER_INCOME")) {
      Bands.Range pct = bands.get(key);
      int year = a.incomeYearOf(key) != null ? a.incomeYearOf(key) : today.getYear();
      Long base = pct == null ? null : benchmarks.monthlyWon(key, year, a.householdSize());
      if (base != null) {
        return pct.times(base * 12 / 100.0);
      }
    }
    return null;
  }
}
