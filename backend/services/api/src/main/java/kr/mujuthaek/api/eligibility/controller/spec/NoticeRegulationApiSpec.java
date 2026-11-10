package kr.mujuthaek.api.eligibility.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.dto.response.NoticeRegulationResponse;

@Tag(
    name = "공고 규제지역 안내",
    description =
        "공고 지역에 걸린 규제지역과 안내 문장이에요. 누구나 부를 수 있어요. " + "판정 결과 화면에 함께 보여 줄 안내라 판정 값은 바꾸지 않아요.")
public interface NoticeRegulationApiSpec {

  @Operation(
      summary = "공고 지역의 규제지역",
      description =
          "공고 지역(의 일부)이 그날 투기과열지구 · 조정대상지역 · 투기지역이면 걸린 지역(areas)과 "
              + "규제 종류마다 안내 문장(guidance)을 줘요. 걸린 규제지역마다 areas[].partial이 있고, 공고 지역(시도 전체, 일반구가 있는 시) 중 일부만 그 규제지역이면 true예요."
              + "확인하는 날(referenceDate)은 접수 시작일, 모르면 오늘이에요. "
              + "주거 공고만 보고, 다른 분야 공고와 전국 공고는 regulated가 false예요.")
  @ApiResponse(responseCode = "200", description = "규제지역 안내")
  @ApiResponse(responseCode = "404", description = "NOTICE_NOT_FOUND — 공고가 없거나 숨김·공개 전이에요")
  NoticeRegulationResponse regulation(@Parameter(description = "공고 ID") UUID id);
}
