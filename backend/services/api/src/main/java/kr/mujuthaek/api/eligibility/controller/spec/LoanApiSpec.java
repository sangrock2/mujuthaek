package kr.mujuthaek.api.eligibility.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import kr.mujuthaek.api.eligibility.dto.request.LoanEvaluateRequest;
import kr.mujuthaek.api.eligibility.model.LoanResult;
import org.springframework.http.ResponseEntity;

@Tag(
    name = "대출 자격 판정",
    description =
        "공고와 상관없이 주택도시기금 대출 상품마다 받을 수 있는지와 그 이유를 줘요. 로그인 없이 부를 수 있어요. "
            + "소득·자산은 POST 본문으로만 받고, 입력과 결과는 저장하지 않고 캐시하지 않아요(no-store).")
public interface LoanApiSpec {

  @Operation(
      summary = "대출 자격 판정",
      description =
          "기준일(asOf)에 쓰는 상품마다 status를 ELIGIBLE(받을 수 있음) · NEEDS_INPUT(확인 필요) · INELIGIBLE(받을 수 없음)으로 줘요. "
              + "받을 수 있음 → 확인 필요 → 받을 수 없음 순이고, 같은 상태끼리는 전세 → 월세 → 구입 순이에요. "
              + "받을 수 없으면 failedConditions에, 확인 필요면 checkReasons와 missingInputs에 이유를 줘요(보낸 값은 넣지 않아요). "
              + "profile은 사업공간·사업 지원 판정의 applicant와 같은 모양에 loan 칸(annualIncomeWon 부부합산 연소득 · "
              + "applicantAnnualIncomeWon 본인 연소득 · netAssetWon 부부합산 순자산 · firstHomePurchase 생애최초 주택구입)을 더해요. "
              + "profile을 비우면 모든 상품이 확인 필요나 받을 수 없음이에요. "
              + "asOf는 대출접수일로 보고, 비우면 오늘(한국 시간)이에요.")
  @ApiResponse(responseCode = "200", description = "상품별 판정")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — 본문을 읽지 못했거나 입력 형식이 맞지 않아요 (금액이 범위 밖, 본인 연소득이 부부합산보다 큼, "
              + "법정동코드·코드 값이 틀림 등)")
  ResponseEntity<LoanResult> evaluate(LoanEvaluateRequest request);
}
