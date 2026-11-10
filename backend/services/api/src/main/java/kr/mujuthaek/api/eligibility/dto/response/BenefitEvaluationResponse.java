package kr.mujuthaek.api.eligibility.dto.response;

import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.rule.Item;
import kr.mujuthaek.api.eligibility.rule.Overall;
import kr.mujuthaek.api.eligibility.rule.benefit.BenefitJudge;

/**
 * 혜택 하나의 판정 (POST /benefits/{id}/evaluate). 그룹 안 조건 중 하나만 충족해도 되고, 그룹은 모두 충족해야 해요. 사용자가 보낸 값은 넣지
 * 않아요.
 *
 * @param reason 사람 확인 전이라 확인 필요로 둔 경우의 이유
 * @param conditions 조건 그룹 (원문 순서). 그룹 안 조건이 둘 이상이면 "다음 중 하나"예요
 * @param notes 판정하지 않는 안내 (중복 수혜 불가, 선정 우선순위)
 * @param annualAmountWon 1년에 받을 수 있는 돈 (대출·금액 모름이면 0)
 */
public record BenefitEvaluationResponse(
    UUID benefitId,
    Overall overall,
    String reason,
    BenefitJudge.Summary summary,
    List<Group> conditions,
    List<String> notes,
    long annualAmountWon) {

  public record Group(int group, String status, List<Item> items) {}
}
