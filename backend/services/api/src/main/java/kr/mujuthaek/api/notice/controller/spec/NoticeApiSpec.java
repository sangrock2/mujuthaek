package kr.mujuthaek.api.notice.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.common.dto.response.CursorPageResponse;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse;
import kr.mujuthaek.api.notice.dto.response.NoticeMapResponse;
import kr.mujuthaek.api.notice.dto.response.NoticeSummaryResponse;
import kr.mujuthaek.api.notice.dto.response.NoticeUnitResponse;
import kr.mujuthaek.api.notice.dto.response.NoticeVersionResponse;

@Tag(
    name = "공고 조회",
    description =
        "공개된 공고의 목록·지도·상세·주택목록·정정 이력이에요. 로그인 없이 누구나 불러요. "
            + "숨김·공개 전 공고는 없는 공고와 같아요. 판정이 섞인 맞춤 목록(POST /api/v1/notices/search)과 판정은 따로 있어요.")
public interface NoticeApiSpec {

  @Operation(
      summary = "공고 목록",
      description =
          "공개된 공고를 정렬 순으로 줘요(다른 공고에 합쳐진 공고는 빠져요). "
              + "목록 값(regionCodes·noticeTypes·providers·statuses)은 쉼표로 이어도 되고 같은 이름을 여러 번 줘도 되며, 하나라도 맞으면 나와요. "
              + "응답의 nextCursor를 다음 요청의 cursor로 넘기면 이어서 받아요(hasNext가 false면 끝). 정렬을 바꾸면 처음부터 다시 받아요. "
              + "예: ?regionCodes=11440,41&tenure=RENT&statuses=APPLYING&applyEndFrom=2026-11-01&applyEndTo=2026-11-30")
  @ApiResponse(responseCode = "200", description = "공고 목록")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — field·sort·tenure·noticeTypes·statuses에 쓸 수 없는 값이거나, regionCodes·날짜 형식이 틀렸거나, "
              + "applyEndFrom이 applyEndTo보다 늦거나, size가 1~100 밖이에요. "
              + "INVALID_CURSOR — cursor를 읽을 수 없거나 다른 정렬로 만든 커서예요")
  CursorPageResponse<NoticeSummaryResponse> list(
      @Parameter(description = "분야: HOUSING(기본) · BUSINESS_SPACE") String field,
      @Parameter(
              description =
                  "지역: 시군구 5자리 또는 시도 2자리. 시도 2자리나 시도 단위 5자리(xx000, 예: 11000 = 서울특별시)는 그 시도의 모든 공고, "
                      + "시군구 5자리는 그 시군구 공고와 그 시군구를 품는 지역 전체 대상 공고가 나와요. 전국 대상 공고는 어느 지역으로도 나와요")
          List<String> regionCodes,
      @Parameter(
              description =
                  "RENT 빌려서 · BUY 사서. PUBLIC_SALE·PRIVATE_SALE이 BUY이고, 그 밖의 유형과 유형을 못 정한 공고가 RENT예요")
          String tenure,
      @Parameter(
              description =
                  "공고 유형 코드. 주거: YOUTH_SAFE_HOUSING · PUBLIC_SUPPORT_PRIVATE_RENTAL · INTEGRATED_PUBLIC_RENTAL · "
                      + "PUBLIC_RENTAL · HAPPY_HOUSING · NATIONAL_RENTAL · PERMANENT_RENTAL · PURCHASE_RENTAL · JEONSE_RENTAL · "
                      + "LONG_TERM_JEONSE · PUBLIC_SALE · PRIVATE_SALE, 사업공간: STARTUP_SPACE · SHOP_RENTAL · MEETING_ROOM")
          List<String> noticeTypes,
      @Parameter(description = "공급 기관 이름 (원문 그대로)") List<String> providers,
      @Parameter(
              description =
                  "접수 상태: UPCOMING 접수예정 · APPLYING 접수중 · CLOSED 마감 · ALWAYS 상시 · UNKNOWN 확인 필요. "
                      + "비우면 마감(CLOSED)을 뺀 전부")
          List<String> statuses,
      @Parameter(description = "DEADLINE(기본) 마감 임박순 · LATEST 최신 공고일순. 마감일·공고일이 없는 공고는 맨 뒤예요")
          String sort,
      @Parameter(description = "마감일이 이날 이후(이날 포함)인 공고만 (yyyy-MM-dd). 마감일을 모르는 공고는 빠져요")
          LocalDate applyEndFrom,
      @Parameter(description = "마감일이 이날 이전(이날 포함)인 공고만 (yyyy-MM-dd). 마감일을 모르는 공고는 빠져요")
          LocalDate applyEndTo,
      @Parameter(description = "이전 응답의 nextCursor. 첫 요청이면 비워요") String cursor,
      @Parameter(description = "한 번에 받을 개수 (기본 20, 1~100)", example = "20") Integer size);

  @Operation(
      summary = "공고 지도",
      description =
          "지도 범위 안 공고의 대표 위치예요. 공고가 300개 이하면 pins로, 넘으면 지역별 묶음(clusters)으로 줘요. "
              + "필터 뜻은 공고 목록과 같지만 값을 검사하지 않아서, 모르는 값을 주면 맞는 공고가 없어요. "
              + "공고 목록과 달리 분야(field)로는 거르지 않아서 주거·사업공간 공고가 함께 나와요(주거만 보려면 noticeTypes로 주거 유형을 줘요).")
  @ApiResponse(responseCode = "200", description = "핀 또는 지역별 묶음")
  @ApiResponse(
      responseCode = "400",
      description = "VALIDATION_FAILED — 좌표가 빠졌거나 숫자가 아니에요. 남서쪽(sw)이 북동쪽(ne)보다 작지 않아요")
  NoticeMapResponse map(
      @Parameter(description = "지도 남서쪽 위도", example = "37.4") double swLat,
      @Parameter(description = "지도 남서쪽 경도", example = "126.8") double swLng,
      @Parameter(description = "지도 북동쪽 위도 (swLat보다 커야 해요)", example = "37.7") double neLat,
      @Parameter(description = "지도 북동쪽 경도 (swLng보다 커야 해요)", example = "127.2") double neLng,
      @Parameter(description = "지도 확대 단계. 묶음일 때 10 미만은 시도, 아니면(없어도) 시군구로 묶어요", example = "12")
          Integer zoom,
      @Parameter(description = "RENT 빌려서 · BUY 사서 (공고 목록과 같아요)") String tenure,
      @Parameter(description = "공고 유형 코드 (공고 목록과 같아요)") List<String> noticeTypes,
      @Parameter(description = "공급 기관 이름 (원문 그대로)") List<String> providers,
      @Parameter(description = "접수 상태 (공고 목록과 같아요). 비우면 마감(CLOSED)을 뺀 전부") List<String> statuses);

  @Operation(
      summary = "공고 상세",
      description =
          "현재 공개 버전의 요약·일정·단지·주택형별 조건·자격 조건과 근거·제출 서류·선정 방식·안내·첨부 링크·보류 항목·위치별 생활·상업 점수·후속 안내예요. "
              + "첨부는 기관 링크만 줘요. 다른 공고에 합쳐진 공고 ID면 남은 공고의 상세를 줘요(header.id가 요청 ID와 달라요).")
  @ApiResponse(responseCode = "200", description = "공고 상세")
  @ApiResponse(responseCode = "404", description = "NOTICE_NOT_FOUND — 공고가 없거나 숨김·공개 전이에요")
  NoticeDetailResponse detail(@Parameter(description = "공고 ID") UUID id);

  @Operation(
      summary = "주택목록 (호별)",
      description =
          "호별 주소·면적·금액이에요. 주택목록이 없는 공고는 빈 목록이에요. 원문 확인 전까지 보류한 호는 빠지고, "
              + "가격만 보류한 호는 보증금·월임대료가 비어요. 응답의 nextCursor를 다음 요청의 cursor로 넘기면 이어서 받아요.")
  @ApiResponse(responseCode = "200", description = "주택목록")
  @ApiResponse(
      responseCode = "400",
      description = "VALIDATION_FAILED — size가 1~100 밖이에요. INVALID_CURSOR — cursor가 올바르지 않아요")
  @ApiResponse(responseCode = "404", description = "NOTICE_NOT_FOUND — 공고가 없거나 숨김·공개 전이에요")
  CursorPageResponse<NoticeUnitResponse> units(
      @Parameter(description = "공고 ID") UUID id,
      @Parameter(description = "단지·건물 하나만 볼 때 (상세의 sites[].id). 없는 ID면 빈 목록") String siteId,
      @Parameter(description = "이전 응답의 nextCursor. 첫 요청이면 비워요") String cursor,
      @Parameter(description = "한 번에 받을 개수 (기본 20, 1~100)", example = "20") Integer size);

  @Operation(
      summary = "정정 이력",
      description =
          "공개한 버전을 첫 버전부터 버전 순으로 줘요. 버전마다 글 종류(NOTICE 모집공고 · CORRECTION 정정), 검수 상태, "
              + "앞 버전과 비교해 바뀐 항목(첫 버전은 빈 목록), 받은 시각이 있어요.")
  @ApiResponse(responseCode = "200", description = "버전 목록")
  @ApiResponse(responseCode = "404", description = "NOTICE_NOT_FOUND — 공고가 없거나 숨김·공개 전이에요")
  List<NoticeVersionResponse> versions(@Parameter(description = "공고 ID") UUID id);
}
