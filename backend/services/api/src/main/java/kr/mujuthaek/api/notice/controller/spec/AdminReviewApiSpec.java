package kr.mujuthaek.api.notice.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.security.Principal;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.notice.dto.request.AdminReviewDecisionRequest;
import kr.mujuthaek.api.notice.dto.response.AdminReviewCountsResponse;
import kr.mujuthaek.api.notice.dto.response.AdminReviewDecisionResponse;
import kr.mujuthaek.api.notice.dto.response.AdminReviewDetailResponse;
import kr.mujuthaek.api.notice.dto.response.AdminReviewListResponse;
import kr.mujuthaek.api.notice.dto.response.AdminReviewQueueResponse;
import kr.mujuthaek.api.notice.dto.response.AdminReviewStatsResponse;

@Tag(
    name = "관리자 공고 검수",
    description =
        "추출 서비스가 공고에서 뽑은 결과를 보고 승인·반려해요. 추출 서비스 검수 API를 이 서버가 대신 불러요. "
            + "권한 NOTICE_REVIEW가 있는 관리자만 부를 수 있고, 대기열(queue)은 kinds마다 그 검수 권한을 봐요.")
public interface AdminReviewApiSpec {

  @Operation(
      summary = "검수 대기열 한 페이지",
      description =
          "공고·혜택 검수를 들어온 시각 순(오래된 것부터)으로 섞어 size건 줘요. 응답의 nextCursor를 다음 요청의 cursor로 넘기면 "
              + "이어서 받아요(null이면 끝). total은 첫 페이지(cursor 없이)에서만 정확해요. "
              + "reason이 FORMAT이면 혜택은 없고, MUST면 혜택은 정책 제보로 다시 연 건만이에요. "
              + "첫 페이지(cursor 없이)는 5초가 지난 뒤 부르면 지난 값을 먼저 주고 뒤에서 새로 받아요. 그래서 마지막으로 받은 지 최대 50초 된 값이 나올 수 있어요. "
              + "줄 값이 없으면(같은 kinds·reason·size로 처음, 이 서버에서 공고 검수를 승인·반려한 직후, 마지막으로 받은 지 50초가 지남) 그 자리에서 받고, 실패하면 503이에요. "
              + "혜택 검수 처리는 첫 페이지에 바로 반영되지 않아요. 다음 페이지(cursor 있음)는 늘 그 자리에서 받아요.")
  @ApiResponse(responseCode = "200", description = "대기열 한 페이지")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — reason이 MUST·CHECK·FORMAT이 아니거나, size가 1~100 밖이거나, cursor가 올바르지 않거나, "
              + "kinds에 고른 종류가 없어요")
  @ApiResponse(responseCode = "503", description = "NOTICE_REVIEW_UNAVAILABLE — 검수 서버에 연결하지 못했어요")
  AdminReviewQueueResponse queue(
      @Parameter(
              description =
                  "보여 줄 종류 NOTICE·BENEFIT를 쉼표로. 비우면 둘 다. 종류마다 그 검수 권한(NOTICE_REVIEW·BENEFIT_REVIEW)이 "
                      + "있어야 하고, 모르는 종류가 있거나 권한이 없으면 403이에요",
              example = "NOTICE,BENEFIT")
          String kinds,
      @Parameter(description = "사유 묶음 MUST·CHECK·FORMAT. 비우면 전부") String reason,
      @Parameter(description = "이전 응답의 nextCursor. 첫 요청이면 비워요") String cursor,
      @Parameter(description = "한 번에 받을 개수 (기본 50, 1~100)") int size);

  @Operation(
      summary = "공고 검수 대기 건수",
      description =
          "대기 건수와 가장 오래 기다린 건이 들어온 시각(대기가 없으면 null)을 줘요. "
              + "5초가 지난 뒤 부르면 지난 값을 먼저 주고 뒤에서 새로 세요. 그래서 마지막으로 센 지 최대 50초 된 값이 나올 수 있어요. "
              + "줄 값이 없으면(처음, 이 서버에서 공고 검수를 승인·반려한 직후, 마지막으로 센 지 50초가 지남) 그 자리에서 세고, 실패하면 503이에요.")
  @ApiResponse(responseCode = "200", description = "대기 건수")
  @ApiResponse(responseCode = "503", description = "NOTICE_REVIEW_UNAVAILABLE — 검수 서버에 연결하지 못했어요")
  AdminReviewCountsResponse counts();

  @Operation(
      summary = "검수 처리 통계 (공고·혜택)",
      description =
          "공고 검수와 혜택 검수 처리를 합쳐서, 최근 days일과 오늘(한국 시간)의 그대로 승인·고쳐서 승인·반려 수와 비율(%), 들어와서 처리되기까지 걸린 시간의 중앙값(분)을 줘요. "
              + "처리한 건이 없으면 비율과 중앙값은 null이에요.")
  @ApiResponse(responseCode = "200", description = "처리 통계")
  @ApiResponse(responseCode = "400", description = "VALIDATION_FAILED — days가 1~90 밖이에요")
  @ApiResponse(responseCode = "503", description = "NOTICE_REVIEW_UNAVAILABLE — 검수 서버에 연결하지 못했어요")
  AdminReviewStatsResponse stats(@Parameter(description = "최근 며칠 (기본 7, 1~90)") int days);

  @Operation(
      summary = "마감이 가까운 공고 검수 대기",
      description =
          "신청 마감이 오늘(한국 시간)부터 days일 안이거나 이미 지난 대기 건을 마감이 이른 것부터 줘요. 마감을 모르는 건은 빠져요. "
              + "1분이 지난 뒤 부르면 지난 값을 먼저 주고 뒤에서 새로 받아요. 그래서 마지막으로 받은 지 최대 10분 된 값이 나올 수 있어요. "
              + "줄 값이 없으면(그 마감 기준일(오늘+days)로 처음, 이 서버에서 공고 검수를 승인·반려한 직후, 마지막으로 받은 지 10분이 지남) "
              + "그 자리에서 받고, 실패하면 503이에요.")
  @ApiResponse(responseCode = "200", description = "마감이 가까운 대기 건")
  @ApiResponse(responseCode = "400", description = "VALIDATION_FAILED — days가 0~30 밖이에요")
  @ApiResponse(responseCode = "503", description = "NOTICE_REVIEW_UNAVAILABLE — 검수 서버에 연결하지 못했어요")
  List<AdminReviewListResponse.Item> urgent(
      @Parameter(description = "오늘부터 며칠 안 마감까지 (기본 3, 0~30)") int days);

  @Operation(
      summary = "공고 검수 상세",
      description =
          "확인할 칸(보류 칸 먼저, 그다음 검증 이슈가 가리키는 칸)과 이유, 원문 근거(쪽·인용문), 처리 기록을 줘요. "
              + "대기 중이면 승인하면 무엇이 바뀌는지(impact)도 줘요.")
  @ApiResponse(responseCode = "200", description = "검수 상세")
  @ApiResponse(responseCode = "404", description = "NOTICE_REVIEW_NOT_FOUND — 없는 검수 항목이에요")
  @ApiResponse(responseCode = "503", description = "NOTICE_REVIEW_UNAVAILABLE — 검수 서버에 연결하지 못했어요")
  AdminReviewDetailResponse detail(@Parameter(description = "검수 작업 ID") UUID id);

  @Operation(
      summary = "공고 검수 승인",
      description =
          "본문은 비워도 돼요. edits가 있으면 그 칸만 고쳐서 승인해요(path는 상세의 fields[].path). 검수 API가 공고 형식을 다시 "
              + "검사하고 결과를 다시 발행해요. 승인에서는 reason을 무시해요. 처리 기록의 검수자는 로그인 계정 ID예요. "
              + "응답의 pendingCount는 처리 뒤 남은 대기 건수예요.")
  @ApiResponse(responseCode = "200", description = "처리 결과")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — 본문이 올바르지 않아요 (reason은 정해진 값, note는 500자까지, edits는 200칸까지, "
              + "path는 비우지 않고 300자까지)")
  @ApiResponse(responseCode = "404", description = "NOTICE_REVIEW_NOT_FOUND — 없는 검수 항목이에요")
  @ApiResponse(
      responseCode = "409",
      description = "NOTICE_REVIEW_CONFLICT — 이미 처리됐거나 새 버전으로 바뀐 검수 항목이에요. 추출 결과가 없는 건도 승인할 수 없어요")
  @ApiResponse(
      responseCode = "422",
      description = "NOTICE_REVIEW_INVALID — 고친 결과가 공고 형식에 맞지 않아요 (detail에 검수 API의 설명)")
  @ApiResponse(responseCode = "503", description = "NOTICE_REVIEW_UNAVAILABLE — 검수 서버에 연결하지 못했어요")
  AdminReviewDecisionResponse approve(
      @Parameter(description = "검수 작업 ID") UUID id,
      AdminReviewDecisionRequest request,
      @Parameter(hidden = true) Principal principal);

  @Operation(
      summary = "공고 검수 반려",
      description =
          "본문은 비워도 돼요. 발행하지 않아요. reason(반려 사유)이 있으면 메모 앞에 [사유]로 붙여 남기고, 반려에서는 edits를 무시해요. "
              + "처리 기록의 검수자는 로그인 계정 ID예요. 응답의 pendingCount는 처리 뒤 남은 대기 건수예요.")
  @ApiResponse(responseCode = "200", description = "처리 결과")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — 본문이 올바르지 않아요 (reason은 정해진 값, note는 500자까지, edits는 200칸까지, "
              + "path는 비우지 않고 300자까지)")
  @ApiResponse(
      responseCode = "409",
      description = "NOTICE_REVIEW_CONFLICT — 대기 중인 검수 항목이 아니에요 (없거나, 이미 처리됐거나, 새 버전으로 바뀜)")
  @ApiResponse(responseCode = "503", description = "NOTICE_REVIEW_UNAVAILABLE — 검수 서버에 연결하지 못했어요")
  AdminReviewDecisionResponse reject(
      @Parameter(description = "검수 작업 ID") UUID id,
      AdminReviewDecisionRequest request,
      @Parameter(hidden = true) Principal principal);
}
