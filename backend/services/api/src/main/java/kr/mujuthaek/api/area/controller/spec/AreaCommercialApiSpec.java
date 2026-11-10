package kr.mujuthaek.api.area.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import kr.mujuthaek.api.area.domain.CommercialScore;

@Tag(name = "상권 점수", description = "공공 상가 위치의 상권 점수(밀도·경쟁·교통)예요. 로그인 없이 불러요.")
public interface AreaCommercialApiSpec {

  @Operation(
      summary = "공공 상가 위치의 상권 점수",
      description =
          "300m 안 점포 수(DENSITY), 같은 업종 경쟁(COMPETITION, 입지계수가 1보다 크면 과밀이라 낮게), "
              + "가장 가까운 도시철도역(TRANSIT) 점수와 그 평균인 총점을 요청 때 계산해요(저장 안 함). "
              + "업종이 없거나 같은 업종이 없는 업종이면, 또는 300m 안 점포가 0이면 COMPETITION이 빠져요. "
              + "창업 공간·회의실처럼 교통만 보면 되는 곳은 GET /api/v1/areas/sites/{siteId}를 써요.")
  @ApiResponse(responseCode = "200", description = "상권 점수")
  @ApiResponse(
      responseCode = "404",
      description = "AREA_SITE_NOT_FOUND — 없는 위치이거나 좌표를 아직 못 찾은 위치예요")
  CommercialScore score(
      @Parameter(description = "area 위치 ID (공고 위치의 siteId)") UUID siteId,
      @Parameter(
              description = "사업 업종. FOOD·CAFE·RETAIL만 같은 업종을 세요(대소문자 무관). 그 밖이거나 비우면 경쟁 점수 없이 계산해요",
              example = "CAFE")
          String industry);
}
