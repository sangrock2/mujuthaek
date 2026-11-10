package kr.mujuthaek.api.eligibility.model;

import java.time.LocalDate;
import java.util.List;
import kr.mujuthaek.api.eligibility.rule.Eligibility;
import kr.mujuthaek.api.eligibility.rule.loan.LoanType;

/**
 * 대출 자격 판정 결과: 기준일에 쓰는 대출 상품 전부. 지원 가능 → 확인 필요 → 불가 순, 같은 상태끼리는 상품 화면 순서(전세 → 월세 → 구입)예요. 저장하지 않아요.
 *
 * @param asOf 판정 기준일
 * @param counts 상태별 상품 수
 */
public record LoanResult(LocalDate asOf, Counts counts, List<Item> items) {

  public LoanResult {
    items = List.copyOf(items);
  }

  public record Counts(int eligible, int needsInput, int ineligible) {}

  /**
   * @param status ELIGIBLE 받을 수 있음 / NEEDS_INPUT 확인 필요 / INELIGIBLE 받을 수 없음
   * @param failedConditions 불가인 이유: 맞지 않는 조건 문장 (사용자가 넣은 값은 넣지 않아요)
   * @param checkReasons 확인이 필요한 이유 문장
   * @param missingInputs 넣으면 결과가 정해질 수 있는 입력
   * @param limitSummary 한도 요약 (참고)
   * @param rateSummary 금리 요약 (참고)
   * @param sourceUrl 주택도시기금 상품안내 원문
   */
  public record Item(
      String productCode,
      String productName,
      LoanType loanType,
      Eligibility status,
      List<String> failedConditions,
      List<String> checkReasons,
      List<MissingInput> missingInputs,
      String limitSummary,
      String rateSummary,
      String sourceUrl) {}
}
