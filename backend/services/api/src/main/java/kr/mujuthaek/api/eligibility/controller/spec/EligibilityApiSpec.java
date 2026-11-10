package kr.mujuthaek.api.eligibility.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.dto.request.EvaluateRequest;
import kr.mujuthaek.api.eligibility.dto.request.PrepareCostRequest;
import kr.mujuthaek.api.eligibility.dto.request.SubscriptionScoreRequest;
import kr.mujuthaek.api.eligibility.dto.response.CriteriaResponse;
import kr.mujuthaek.api.eligibility.dto.response.NoticeEvaluationResponse;
import kr.mujuthaek.api.eligibility.rule.PrepareCost;
import kr.mujuthaek.api.eligibility.rule.SubscriptionScore;
import org.springframework.http.ResponseEntity;

@Tag(
    name = "공고 판정",
    description =
        "공고 하나의 자격 판정, 보증금으로 준비할 돈·청약 가점 계산, 판정 기준 금액이에요. 로그인 없이 부를 수 있어요. "
            + "판정 입력은 저장하지 않고, 판정·계산 결과는 캐시하지 않아요(no-store).")
public interface EligibilityApiSpec {

  @Operation(
      summary = "보증금으로 준비할 돈",
      description =
          "depositWon(보증금)에서 받을 수 있는 대출 중 가장 큰 금액을 뺀 돈(prepareWon)과 고른 대출(loan)을 줘요. "
              + "소득·자산을 몰라 더 많이 빌려주는 대출을 판정할 수 없으면 prepareWon 대신 note(INCOME_UNKNOWN · "
              + "ASSET_UNKNOWN)를 줘요. 쓸 수 있는 돈과 비교(모자란 금액)는 화면이 해요.")
  @ApiResponse(responseCode = "200", description = "준비할 돈")
  @ApiResponse(
      responseCode = "400",
      description = "VALIDATION_FAILED — applicant·depositWon이 없거나 형식이 맞지 않아요 (depositWon은 0 이상)")
  ResponseEntity<PrepareCost.Result> prepareCost(PrepareCostRequest request);

  @Operation(
      summary = "공고 자격 판정",
      description =
          "공고의 판정 틀로 공급 대상별 결과와 조건별 근거, 주택형별 준비할 돈을 줘요. "
              + "overall은 ELIGIBLE(지원 가능) · NEEDS_INPUT(확인 필요) · INELIGIBLE(지원 불가)이고, "
              + "대상 중 하나라도 지원 가능이면 지원 가능, 아니면 확인 필요가 있으면 확인 필요예요. "
              + "판정 틀이 아직 없거나 자격 조건을 다 읽지 못한 공고는 확인 필요이고 reason에 이유를 줘요. "
              + "missingInputs는 넣으면 판정이 바뀌는 입력 칸이에요. 응답에는 보낸 소득·자산 값을 넣지 않아요.")
  @ApiResponse(responseCode = "200", description = "판정 결과")
  @ApiResponse(responseCode = "400", description = "VALIDATION_FAILED — applicant가 없거나 형식이 맞지 않아요")
  @ApiResponse(responseCode = "404", description = "NOTICE_NOT_FOUND — 공고가 없거나 숨김·공개 전이에요")
  ResponseEntity<NoticeEvaluationResponse> evaluateNotice(
      @Parameter(description = "공고 ID") UUID id, EvaluateRequest request);

  @Operation(
      summary = "청약 가점",
      description =
          "무주택 기간(최대 32점) · 부양가족 수(최대 35점) · 청약통장 가입 기간(최대 17점)을 더해 84점 만점으로 계산해요. "
              + "판정 입력(구간 값)이 아니라 가점용 정확한 값(연월 단위)을 받아요. "
              + "빈 항목은 점수 없이(null) 이유와 넣을 칸(missingInputs)을 주고, 총점은 아는 항목의 합이에요. "
              + "referenceDate(모집공고일)를 비우면 오늘 기준이에요.")
  @ApiResponse(responseCode = "200", description = "가점")
  @ApiResponse(responseCode = "400", description = "VALIDATION_FAILED — applicant가 없거나 형식이 맞지 않아요")
  ResponseEntity<SubscriptionScore.Score> subscriptionScore(SubscriptionScoreRequest request);

  @Operation(
      summary = "판정 기준 금액",
      description =
          "연도별 가구원 수별 기준 중위소득·도시근로자 월평균소득 월액, 순위 요건, 총자산·자동차가액 구간 경계를 줘요. "
              + "판정 입력의 incomeYear와 소득 % 구간·자산 구간을 이 값으로 계산해요. "
              + "도시근로자 소득은 그해 값이 없으면 가장 가까운 앞 해(2년까지) 값이고 그 연도는 urbanWorkerIncomeYear예요. "
              + "하루 캐시돼요.")
  @ApiResponse(responseCode = "200", description = "기준 금액")
  @ApiResponse(responseCode = "404", description = "CRITERIA_NOT_FOUND — 그 연도의 판정 기준값이 아직 없어요")
  ResponseEntity<CriteriaResponse> criteria(
      @Parameter(description = "기준 연도. 비우면 오늘 쓰는 가장 최근 연도", example = "2026") Integer year,
      @Parameter(description = "공고 유형. 그 유형의 순위 요건이 있으면 그것을, 없으면 기본 순위 요건을 줘요") String noticeType);
}
