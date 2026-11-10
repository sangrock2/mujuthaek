package kr.mujuthaek.api.eligibility.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.dto.request.BenefitSearchRequest;
import kr.mujuthaek.api.eligibility.dto.request.EvaluateRequest;
import kr.mujuthaek.api.eligibility.dto.response.BenefitEvaluationResponse;
import kr.mujuthaek.api.eligibility.dto.response.BenefitSearchResponse;
import org.springframework.http.ResponseEntity;

@Tag(
    name = "혜택 맞춤 목록·판정",
    description =
        "판정 입력으로 고른 혜택 목록과 혜택 하나의 판정이에요 (공개 상세는 GET /api/v1/benefits/{id}). "
            + "로그인 없이 부를 수 있어요. 판정 입력은 저장하지 않고 응답은 캐시하지 않아요(no-store).")
public interface BenefitSearchApiSpec {

  @Operation(
      summary = "혜택 맞춤 목록",
      description =
          "찾아볼 지역(비우면 전체, 있으면 전국 혜택 + 그 지역 혜택)에서 신청할 수 있거나 곧 열리는 혜택을 모두 판정하고, "
              + "지원 불가를 뺀 목록을 줘요. summary에는 상태별 개수와 지원 가능한 혜택으로 1년에 받을 수 있는 돈(대출 빼고), "
              + "categoryCounts에는 분야 필터를 걸기 전 분야별 지원 가능·확인 필요 수가 있어요. "
              + "sort는 RECOMMENDED(기본: 지원 가능 → 1년에 받는 돈 많은 순 → 마감 임박) · DEADLINE · AMOUNT예요. "
              + "응답의 nextCursor를 다음 요청의 cursor로 넘기면 이어서 받아요(hasNext가 false면 끝).")
  @ApiResponse(responseCode = "200", description = "혜택 목록")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — 본문 형식이 맞지 않아요 (size 1~100, sort·categories·regionCodes 허용 값, applicant 값). "
              + "INVALID_CURSOR — cursor가 올바르지 않거나 다른 정렬로 만든 거예요")
  ResponseEntity<BenefitSearchResponse> search(BenefitSearchRequest request);

  @Operation(
      summary = "혜택 하나 판정",
      description =
          "조건 그룹별 결과를 원문 순서로 줘요. 그룹 안 조건은 하나만 충족해도 되고, 그룹은 모두 충족해야 해요. "
              + "overall은 ELIGIBLE(지원 가능) · NEEDS_INPUT(확인 필요) · INELIGIBLE(지원 불가)이에요. "
              + "사람 확인 전 혜택은 지원 가능이어도 확인 필요로 두고 reason에 이유를 줘요. "
              + "notes는 판정하지 않는 안내(중복 수혜 불가, 선정 우선순위)예요.")
  @ApiResponse(responseCode = "200", description = "판정 결과")
  @ApiResponse(responseCode = "400", description = "VALIDATION_FAILED — applicant가 없거나 형식이 맞지 않아요")
  @ApiResponse(responseCode = "404", description = "BENEFIT_NOT_FOUND — 혜택이 없거나 숨긴 혜택이에요")
  ResponseEntity<BenefitEvaluationResponse> evaluate(
      @Parameter(description = "혜택 ID") UUID id, EvaluateRequest request);
}
