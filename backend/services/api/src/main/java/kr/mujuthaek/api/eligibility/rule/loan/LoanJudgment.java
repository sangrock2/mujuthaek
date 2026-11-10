package kr.mujuthaek.api.eligibility.rule.loan;

import java.util.List;
import java.util.Set;
import kr.mujuthaek.api.eligibility.rule.Eligibility;

/**
 * 대출 상품 하나를 이 사용자에 맞춰 본 결과 (판정 엔진 안쪽). 저장하지 않고, 서비스가 LoanResult로 바꿔서 돌려줘요.
 *
 * @param status 조건을 모두 충족하면 지원 가능, 하나라도 불충족이면 불가, 그 밖에 모르는 값이 있으면 확인 필요
 * @param failed 불충족인 조건 (불가인 이유). 사용자가 넣은 값은 넣지 않아요
 * @param unclear 확인이 필요한 이유
 * @param missing 확인 필요를 없애는 데 필요한 입력
 */
public record LoanJudgment(
    LoanTerms terms,
    Eligibility status,
    List<String> failed,
    List<String> unclear,
    Set<LoanInput> missing) {

  public LoanJudgment {
    failed = List.copyOf(failed);
    unclear = List.copyOf(unclear);
    missing = Set.copyOf(missing);
  }
}
