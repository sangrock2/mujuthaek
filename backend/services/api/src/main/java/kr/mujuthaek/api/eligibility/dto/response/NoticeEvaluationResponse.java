package kr.mujuthaek.api.eligibility.dto.response;

import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.rule.Judge;
import kr.mujuthaek.api.eligibility.rule.Overall;
import kr.mujuthaek.api.eligibility.rule.PrepareCost;

/**
 * 공고 판정 (POST /eligibility/notices/{id}/evaluate). 사용자가 보낸 소득·자산 값은 넣지 않고 기준과 결과만 줘요.
 *
 * @param overall 대상 중 하나라도 ELIGIBLE이면 ELIGIBLE, 아니면 NEEDS_INPUT이 있으면 NEEDS_INPUT, 그 밖 INELIGIBLE
 * @param reason 판정할 수 없을 때 이유 (판정 틀이 아직 없음 등). 판정했으면 null
 * @param targets 공급 대상별 결과 (대상 id·이름·결과·조건 수 요약·조건별 결과)
 * @param missingInputs 넣으면 판정이 바뀌는 입력 칸
 * @param unitTypes 주택형별 준비할 돈 (화면의 "신청 가능만" 필터는 eligible로 걸러요)
 */
public record NoticeEvaluationResponse(
    UUID noticeId,
    Overall overall,
    String reason,
    List<Judge.Target> targets,
    List<String> missingInputs,
    List<UnitType> unitTypes) {

  /**
   * @param eligible 공고 판정이 지원 가능인지 (주택형별 대상 구분은 아직 없어요)
   */
  public record UnitType(String houseType, boolean eligible, PrepareCost.Result prepareCost) {}
}
