package kr.mujuthaek.api.eligibility.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.security.Principal;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.dto.request.AdminCriteriaRequest;
import kr.mujuthaek.api.eligibility.dto.request.RegulatedAreaRequest;
import kr.mujuthaek.api.eligibility.dto.response.AdminCriteriaResponse;
import kr.mujuthaek.api.eligibility.dto.response.CriteriaUsageResponse;
import kr.mujuthaek.api.eligibility.dto.response.RegulatedAreaResponse;

@Tag(
    name = "관리자 판정 기준값",
    description =
        "판정에 쓰는 연도별 기준값(기준 중위소득·도시근로자 월평균소득·순위 요건)과 규제지역을 넣고 바꿔요. "
            + "권한 CRITERIA가 있는 관리자만 불러요 (바꾼 기록 보기는 CRITERIA 또는 ACTIVITY).")
public interface AdminCriteriaApiSpec {

  @Operation(
      summary = "기준값 연도별 목록",
      description =
          "한 종류의 연도별 값을 최근 연도부터 줘요. state는 IN_EFFECT(오늘 판정에 쓰는 값) · "
              + "SCHEDULED(쓰기 시작하는 날이 아직 안 옴, 예약) · PAST(지난 해)예요.")
  @ApiResponse(responseCode = "200", description = "연도별 값")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — kind가 MEDIAN_INCOME·URBAN_WORKER_INCOME·RANK_CRITERIA 중 하나가 아니에요")
  AdminCriteriaResponse criteria(
      @Parameter(
              description =
                  "기준값 종류: MEDIAN_INCOME(기준 중위소득) · URBAN_WORKER_INCOME(도시근로자 월평균소득) · "
                      + "RANK_CRITERIA(순위 요건)",
              example = "MEDIAN_INCOME")
          String kind);

  @Operation(
      summary = "한 해 기준값 넣기·바꾸기",
      description =
          "validFrom을 비우면 그해 1월 1일이고, 미래 날짜면 그날부터 판정에 쓰여요(예약). "
              + "data는 소득 기준이면 {\"monthlyWon\": {\"1\": …}}(1인 가구부터 가구원 수별 월 금액, 0보다 큰 원 단위 정수), "
              + "순위 요건이면 ranks 목록이나 byNoticeType이 있어야 해요. "
              + "값의 모양만 검사하니 금액은 근거(source: 고시 번호·공고 이름)와 함께 확인해서 넣어요. "
              + "이미 있는 해를 바꾸면 바꾸기 전 값이 바꾼 기록에 남아요. 저장한 뒤 그 종류의 연도별 값 전체를 줘요.")
  @ApiResponse(responseCode = "200", description = "저장한 뒤의 연도별 값")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — kind가 허용 값이 아니거나, year가 2000~2200 밖이거나, validFrom이 그해 밖이거나, "
              + "data가 없거나 모양이 맞지 않아요 (source는 300자까지)")
  AdminCriteriaResponse save(
      @Parameter(
              description = "기준값 종류: MEDIAN_INCOME · URBAN_WORKER_INCOME · RANK_CRITERIA",
              example = "MEDIAN_INCOME")
          String kind,
      @Parameter(description = "기준 연도 (2000~2200)", example = "2027") int year,
      AdminCriteriaRequest request,
      @Parameter(hidden = true) Principal principal);

  @Operation(summary = "기준값 바꾼 기록", description = "바뀌기 전 값과 바뀐 때·바꾼 관리자를 최근 것부터 100개까지 줘요.")
  @ApiResponse(responseCode = "200", description = "바꾼 기록")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — kind가 MEDIAN_INCOME·URBAN_WORKER_INCOME·RANK_CRITERIA 중 하나가 아니에요")
  AdminCriteriaResponse.Changes history(
      @Parameter(
              description = "기준값 종류: MEDIAN_INCOME · URBAN_WORKER_INCOME · RANK_CRITERIA",
              example = "MEDIAN_INCOME")
          String kind);

  @Operation(
      summary = "기준값을 쓰는 공고 수",
      description =
          "열린 주거 공고 · 사업공간 · 창업지원 사업 중 판정 틀이 이 기준을 쓰는 수를 분야별로 줘요. "
              + "URBAN_WORKER_INCOME은 도시근로자 가구당 월평균소득 기준도 세고, RANK_CRITERIA는 신청 순위가 있는 판정 틀을 세요.")
  @ApiResponse(responseCode = "200", description = "분야별 수")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — kind가 MEDIAN_INCOME·URBAN_WORKER_INCOME·RANK_CRITERIA 중 하나가 아니에요")
  CriteriaUsageResponse usage(
      @Parameter(
              description = "기준값 종류: MEDIAN_INCOME · URBAN_WORKER_INCOME · RANK_CRITERIA",
              example = "MEDIAN_INCOME")
          String kind);

  @Operation(summary = "규제지역 목록", description = "지정일 최근 순이에요. 응답의 active는 오늘 지정 중인지예요.")
  List<RegulatedAreaResponse> regulatedAreas(
      @Parameter(description = "true면 오늘 지정 중인 것만, false(기본)면 해제된 것까지 전부") boolean active);

  @Operation(
      summary = "규제지역 지정",
      description =
          "regionCode는 시군구 5자리(시도 전체면 xx000)이고, kind는 SPECULATION_OVERHEATED(투기과열지구) · "
              + "ADJUSTMENT_TARGET(조정대상지역) · SPECULATION(투기지역)이에요. 지정 중이면 validUntil(해제일)을 비워요. "
              + "일부 지역만이면 scopeNote에 적어요.")
  @ApiResponse(responseCode = "200", description = "지정한 규제지역")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — 본문 형식이 맞지 않거나(regionCode 5자리 숫자, kind·validFrom 필수, scopeNote·source 300자까지) "
              + "해제일이 지정일보다 앞서요")
  RegulatedAreaResponse add(
      RegulatedAreaRequest request, @Parameter(hidden = true) Principal principal);

  @Operation(summary = "규제지역 해제", description = "until을 해제일로 남겨요.")
  @ApiResponse(responseCode = "200", description = "해제한 규제지역")
  @ApiResponse(responseCode = "400", description = "VALIDATION_FAILED — 해제일이 지정일보다 앞서요")
  @ApiResponse(responseCode = "404", description = "NOT_FOUND — 규제지역이 없어요")
  RegulatedAreaResponse end(
      @Parameter(description = "규제지역 ID") UUID id,
      @Parameter(description = "해제일 (YYYY-MM-DD). 비우면 오늘(한국 시간)") LocalDate until,
      @Parameter(hidden = true) Principal principal);
}
