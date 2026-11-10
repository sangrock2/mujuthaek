package kr.mujuthaek.api.common.region.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import kr.mujuthaek.api.common.region.RegionQueryService.Region;
import kr.mujuthaek.api.common.region.RegionQueryService.RegionTree;
import org.springframework.http.ResponseEntity;
import org.springframework.web.context.request.WebRequest;

@Tag(name = "지역 코드", description = "시·도와 시·군·구 공통 코드예요. 로그인 없이 받고, 하루 캐시와 ETag가 붙어요.")
public interface RegionApiSpec {

  @Operation(
      summary = "시·도와 시·군·구 전체",
      description =
          "지금 유효한 시·도와 그 아래 시·군·구를 코드 순으로 줘요. baseDate는 코드표 기준일이에요. "
              + "If-None-Match가 지금 ETag와 같으면 본문 없이 304예요.")
  @ApiResponse(responseCode = "200", description = "코드표")
  @ApiResponse(responseCode = "304", description = "바뀐 것 없음 (If-None-Match가 같을 때)")
  ResponseEntity<RegionTree> all(@Parameter(hidden = true) WebRequest request);

  @Operation(
      summary = "지역 코드 하나",
      description = "코드의 이름과 단계(시·도/시·군·구)를 줘요. 없어진 코드면 valid가 false이고 replacedBy에 바뀐 코드가 있어요.")
  @ApiResponse(responseCode = "200", description = "지역 코드")
  @ApiResponse(responseCode = "400", description = "VALIDATION_FAILED — 2자리·5자리 숫자가 아니에요")
  @ApiResponse(responseCode = "404", description = "NOT_FOUND — 없는 지역 코드예요")
  ResponseEntity<Region> one(
      @Parameter(description = "2자리(시·도) 또는 5자리(시·군·구) 지역 코드", example = "11680") String code);
}
