package kr.mujuthaek.api.area.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import kr.mujuthaek.api.area.domain.AreaCriteria;
import kr.mujuthaek.api.area.domain.SiteDetail;
import kr.mujuthaek.api.area.dto.request.AreaScoreRequest;
import kr.mujuthaek.api.area.dto.response.AreaScoreResponse;
import org.springframework.http.ResponseEntity;

@Tag(
    name = "생활권 정보",
    description = "공고 위치(siteId)의 생활권 지표·항목 점수, 점수 기준표, 내 가중치로 계산하는 총점이에요. 로그인 없이 불러요.")
public interface AreaApiSpec {

  @Operation(
      summary = "위치 하나의 생활권 정보",
      description =
          "좌표, 세권 지표(역·버스·학교·공원·병원·편의시설), 생활권 항목 점수, 세권 태그를 줘요. 미리 계산해 둔 값만 읽어요. "
              + "approximate가 true면 법정동 대표점 기준이라 지표·점수도 그 점 기준이에요.")
  @ApiResponse(responseCode = "200", description = "생활권 정보")
  @ApiResponse(
      responseCode = "404",
      description = "AREA_SITE_NOT_FOUND — 없는 위치이거나 좌표를 아직 못 찾은 위치예요")
  SiteDetail site(@Parameter(description = "area 위치 ID (공고 목록·상세의 siteId)") UUID siteId);

  @Operation(
      summary = "생활권 총점 계산",
      description =
          "내 항목별 가중치(0~10)와 직장 위치로 위치마다 총점·항목 점수·직장까지 직선거리를 계산해요. "
              + "가중치·직장 위치가 들어가서 저장·캐시하지 않아요(Cache-Control: no-store). "
              + "siteIds는 1~50개이고, 응답 items는 받은 순서예요. 없는 위치는 빠져요. 좌표를 아직 못 찾은 위치는 빠지지 않고 total이 null, categoryScores가 빈 값으로 와요. "
              + "총점은 Σ(항목 점수 × 가중치) ÷ 가중치 합이고, 가중치가 모두 0이거나 없으면 같은 비중이에요. "
              + "직장(WORK) 점수는 workplace를 보냈을 때만 있고, 길찾기를 쓰지 않아 commuteMinutes는 늘 null이에요.")
  @ApiResponse(responseCode = "200", description = "위치별 점수 (items)")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — siteIds가 비었거나 50개를 넘거나, 가중치가 0~10 밖이거나, workplace의 lat·lng가 없거나 범위 밖이에요")
  ResponseEntity<AreaScoreResponse> score(AreaScoreRequest request);

  @Operation(
      summary = "점수 기준표와 데이터 출처",
      description =
          "지표별 점수 구간(xs → ys, 사이는 직선, 양끝 밖은 끝 값), 생활권 항목을 이루는 지표와 비중, 데이터 출처를 줘요. " + "하루 캐시가 붙어요.")
  ResponseEntity<AreaCriteria> criteria();
}
