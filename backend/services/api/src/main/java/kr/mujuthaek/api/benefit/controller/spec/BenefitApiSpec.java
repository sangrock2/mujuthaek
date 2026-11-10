package kr.mujuthaek.api.benefit.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import kr.mujuthaek.api.benefit.dto.response.BenefitDetailResponse;

@Tag(
    name = "혜택 상세",
    description =
        "혜택(정책)의 공개 정보예요. 로그인 없이 불러요. 내 조건 판정은 POST /api/v1/benefits/search · /api/v1/benefits/{id}/evaluate예요.")
public interface BenefitApiSpec {

  @Operation(
      summary = "혜택 상세",
      description =
          "지원 내용, 신청 기간과 신청 상태·마감까지 남은 날(오늘 날짜로 계산), 신청 방법·서류·문의, 자격 조건 원문과 근거, 원문 주소를 줘요. "
              + "판정 결과는 없어요. 금액은 원이에요.")
  @ApiResponse(responseCode = "200", description = "혜택 상세")
  @ApiResponse(responseCode = "404", description = "BENEFIT_NOT_FOUND — 없거나 숨긴(HIDDEN) 혜택이에요")
  BenefitDetailResponse detail(@Parameter(description = "혜택 ID") UUID id);
}
