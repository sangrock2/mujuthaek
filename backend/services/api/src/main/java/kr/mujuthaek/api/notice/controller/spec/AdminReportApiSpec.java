package kr.mujuthaek.api.notice.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.security.Principal;
import java.util.UUID;
import kr.mujuthaek.api.notice.dto.request.AdminReportResolveRequest;
import kr.mujuthaek.api.notice.dto.response.AdminReportDetailResponse;
import kr.mujuthaek.api.notice.dto.response.AdminReportListResponse;
import kr.mujuthaek.api.notice.dto.response.AdminReportQueueResponse;
import kr.mujuthaek.api.notice.dto.response.AdminReportReviewResponse;

@Tag(
    name = "관리자 제보 처리",
    description =
        "회원이 보낸 공고·창업지원 사업·혜택 제보와 일반 제보를 관리자가 확인하고 답해요. 권한 REPORTS가 있는 관리자만 부를 수 있어요. "
            + "생활권 제보는 따로 있어요(/api/admin/area-reports).")
public interface AdminReportApiSpec {

  @Operation(
      summary = "제보 목록",
      description =
          "최근 것부터 최대 100건과 상태별 전체 건수(counts)를 줘요. targetType은 NOTICE · PROGRAM · BENEFIT · GENERAL(일반 제보)이에요. "
              + "제보한 회원이 누구인지는 주지 않아요.")
  @ApiResponse(responseCode = "200", description = "제보 목록과 상태별 건수")
  @ApiResponse(
      responseCode = "400",
      description = "VALIDATION_FAILED — status가 NEW·DOING·DONE이 아니에요")
  AdminReportListResponse list(
      @Parameter(description = "NEW 새 제보 · DOING 처리 중 · DONE 처리 끝. 비우면 모두") String status);

  @Operation(summary = "상태별 제보 건수", description = "사이드바 숫자예요.")
  AdminReportListResponse.Counts counts();

  @Operation(
      summary = "제보 대기열 한 페이지",
      description =
          "공고·혜택·사업·일반 제보와 생활권 제보를 한 목록으로 섞어, 들어온 시각 최신순으로 size건 줘요(무한 스크롤). "
              + "상태마다 따로 받아요. kind가 REPORT면 /api/admin/reports/{id}, AREA면 /api/admin/area-reports/{id}로 상세를 봐요. "
              + "응답의 nextCursor를 다음 요청의 cursor로 그대로 넘기면 이어서 받아요(null이면 끝). "
              + "상태별 건수는 /api/admin/reports/counts와 /api/admin/area-reports/counts예요.")
  @ApiResponse(responseCode = "200", description = "대기열 한 페이지")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — status가 NEW·DOING·DONE이 아니거나, size가 1~100 밖이거나, cursor가 올바르지 않아요")
  AdminReportQueueResponse queue(
      @Parameter(description = "처리 상태 NEW(처리 전) · DOING(처리 중) · DONE(끝남). 기본 NEW", example = "NEW")
          String status,
      @Parameter(description = "이전 응답의 nextCursor. 첫 요청이면 비워요") String cursor,
      @Parameter(description = "한 번에 받을 개수 (기본 20, 1~100)", example = "20") int size);

  @Operation(
      summary = "제보 상세",
      description =
          "제보 한 건과 설명 전체, 같은 대상·칸의 다른 제보(맞다고 한 값이나 설명이 있는 것만), 처리 결과·답·처리한 관리자, "
              + "「고치기」로 다시 연 검수 ID(reviewId)예요. 제보한 회원이 누구인지는 주지 않아요.")
  @ApiResponse(responseCode = "200", description = "제보 상세")
  @ApiResponse(responseCode = "404", description = "NOTICE_REPORT_NOT_FOUND — 제보가 없어요")
  AdminReportDetailResponse detail(@Parameter(description = "제보 ID") UUID id);

  @Operation(
      summary = "처리 시작",
      description = "새 제보(NEW)를 처리 중(DOING)으로 바꾸고 처리한 관리자로 남겨요. 이미 처리 중이거나 끝났으면 그대로 두고 상세를 줘요.")
  @ApiResponse(responseCode = "200", description = "제보 상세")
  @ApiResponse(responseCode = "404", description = "NOTICE_REPORT_NOT_FOUND — 제보가 없어요")
  AdminReportDetailResponse start(
      @Parameter(description = "제보 ID") UUID id, @Parameter(hidden = true) Principal principal);

  @Operation(
      summary = "고치기: 검수 다시 열기",
      description =
          "공고 제보면 그 공고의 가장 새로 발행한 추출 결과를 공고 검수 대기로, 혜택 제보면 그 정책의 가장 새 정제 결과를 혜택 검수 대기로 다시 열어요. "
              + "이 제보와 같은 대상·칸의 처리 전 제보에 그 검수를 잇고, 새 제보면 처리 중으로 바꿔요. "
              + "이미 대기 중인 검수가 있으면 그것을 이어요(reopened가 false). "
              + "관리자는 reviewId로 검수 화면(공고는 /api/admin/reviews/{id}, 혜택은 /api/admin/benefit-reviews/{id})에서 칸을 고쳐 승인한 뒤 "
              + "처리 끝(resolve)으로 제보를 끝내요.")
  @ApiResponse(responseCode = "200", description = "다시 연 검수")
  @ApiResponse(
      responseCode = "404",
      description =
          "NOTICE_REPORT_NOT_FOUND — 제보가 없어요. NOTICE_NOT_FOUND — 제보한 공고가 없거나 공개 전이에요. "
              + "NOTICE_REVIEW_NOT_FOUND — 검수 서버에 다시 열 결과가 없어요")
  @ApiResponse(
      responseCode = "409",
      description = "CONFLICT — 이미 처리한 제보예요. 일반 제보와 창업지원 사업 제보는 「고치기」가 없어요")
  @ApiResponse(responseCode = "503", description = "NOTICE_REVIEW_UNAVAILABLE — 검수 서버에 연결하지 못했어요")
  AdminReportReviewResponse review(
      @Parameter(description = "제보 ID") UUID id, @Parameter(hidden = true) Principal principal);

  @Operation(
      summary = "처리 끝",
      description =
          "result는 FIXED(고침) · KEPT(원문대로 둠)예요. group이 비었거나 true면 같은 대상·칸의 처리 전 제보도 같은 결과·답으로 끝내요"
              + "(일반 제보는 묶지 않아요). reply가 있으면 끝낸 제보마다 답장 이벤트를 알림 쪽에 넘기고, 비우면 답장을 보내지 않아요.")
  @ApiResponse(responseCode = "200", description = "제보 상세")
  @ApiResponse(
      responseCode = "400",
      description = "VALIDATION_FAILED — result가 없거나 FIXED·KEPT가 아니에요. reply가 1000자를 넘었어요")
  @ApiResponse(responseCode = "404", description = "NOTICE_REPORT_NOT_FOUND — 제보가 없어요")
  @ApiResponse(responseCode = "409", description = "CONFLICT — 이미 처리한 제보예요")
  AdminReportDetailResponse resolve(
      @Parameter(description = "제보 ID") UUID id,
      AdminReportResolveRequest request,
      @Parameter(hidden = true) Principal principal);
}
