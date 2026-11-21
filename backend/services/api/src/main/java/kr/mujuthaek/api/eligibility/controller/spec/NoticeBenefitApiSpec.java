package kr.mujuthaek.api.eligibility.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.dto.request.EvaluateRequest;
import kr.mujuthaek.api.eligibility.dto.response.BenefitSearchResponse;
import org.springframework.http.ResponseEntity;

@Tag(name = "공고 연계 혜택", description = "주거 공고와 함께 확인할 혜택을 조회해요.")
public interface NoticeBenefitApiSpec {

  @Operation(
      summary = "공고와 함께 확인할 혜택",
      description = "입주 지역으로 후보를 좁히고 현재 신청 조건으로 판정해요. 입력 값은 저장하지 않아요.")
  @ApiResponse(responseCode = "200", description = "관련 혜택 목록")
  @ApiResponse(responseCode = "404", description = "NOTICE_NOT_FOUND — 공개 공고가 없어요")
  ResponseEntity<List<BenefitSearchResponse.Item>> related(
      @Parameter(description = "공고 ID") UUID id, EvaluateRequest request);
}
