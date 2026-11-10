package kr.mujuthaek.api.notice.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.security.Principal;
import java.util.UUID;
import kr.mujuthaek.api.notice.dto.request.AdminReviewDecisionRequest;
import kr.mujuthaek.api.notice.dto.response.AdminBenefitReviewCountsResponse;
import kr.mujuthaek.api.notice.dto.response.AdminBenefitReviewDetailResponse;
import kr.mujuthaek.api.notice.dto.response.AdminReviewDecisionResponse;

@Tag(
    name = "관리자 혜택 검수",
    description =
        "확인 필요로 나간 주거·이주 정책(혜택) 정제 결과와 정책 제보로 다시 연 결과를 승인·반려해요. "
            + "추출 서비스 혜택 검수 API를 이 서버가 대신 불러요. 권한 BENEFIT_REVIEW가 있는 관리자만 부를 수 있어요.")
public interface AdminBenefitReviewApiSpec {

  @Operation(
      summary = "혜택 검수 대기 건수",
      description =
          "사이드바·개요에 쓰는 대기 건수만 줘요(목록 전체를 받지 않아요). "
              + "5초가 지난 뒤 부르면 지난 값을 먼저 주고 뒤에서 새로 세요. 그래서 마지막으로 센 지 최대 50초 된 값이 나올 수 있어요. "
              + "줄 값이 없으면(처음, 이 서버에서 혜택 검수를 승인·반려한 직후, 마지막으로 센 지 50초가 지남) 그 자리에서 세고, 실패하면 503이에요.")
  @ApiResponse(responseCode = "200", description = "대기 건수 (benefitPending)")
  @ApiResponse(responseCode = "503", description = "NOTICE_REVIEW_UNAVAILABLE — 검수 서버에 연결하지 못했어요")
  AdminBenefitReviewCountsResponse counts();

  @Operation(
      summary = "혜택 검수 상세",
      description =
          "정제 결과(result)와 받은 원문(source)을 나란히 주고, 처리했으면 결정자·시각과 칸별 수정(edits)도 줘요. "
              + "칸별 수정의 path는 result 기준 JSON Pointer예요.")
  @ApiResponse(responseCode = "200", description = "검수 상세")
  @ApiResponse(responseCode = "404", description = "NOTICE_REVIEW_NOT_FOUND — 없는 혜택 검수 항목이에요")
  @ApiResponse(responseCode = "503", description = "NOTICE_REVIEW_UNAVAILABLE — 검수 서버에 연결하지 못했어요")
  AdminBenefitReviewDetailResponse detail(@Parameter(description = "혜택 검수 ID") UUID id);

  @Operation(
      summary = "혜택 검수 승인",
      description =
          "본문은 비워도 돼요. edits가 있으면 그 칸만 고친 뒤(path 예: /conditions/0/value) 확인 필요를 풀어 다시 내보내요. "
              + "사용자 알림은 보내지 않아요. 승인에서는 reason을 무시해요. 처리 기록의 검수자는 로그인 계정 ID예요. "
              + "응답의 pendingCount는 처리 뒤 남은 혜택 검수 대기 건수예요.")
  @ApiResponse(responseCode = "200", description = "처리 결과")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — 본문이 올바르지 않아요 (reason은 정해진 값, note는 500자까지, edits는 200칸까지, "
              + "path는 비우지 않고 300자까지)")
  @ApiResponse(responseCode = "404", description = "NOTICE_REVIEW_NOT_FOUND — 없는 혜택 검수 항목이에요")
  @ApiResponse(
      responseCode = "409",
      description = "NOTICE_REVIEW_CONFLICT — 이미 처리됐거나 더 새 버전 결과가 나간 검수 항목이에요")
  @ApiResponse(
      responseCode = "422",
      description =
          "NOTICE_REVIEW_INVALID — 고칠 수 없는 칸(원본·버전·출처·품질)이거나 고친 결과가 형식에 맞지 않아요 (detail에 검수 API의 설명)")
  @ApiResponse(responseCode = "503", description = "NOTICE_REVIEW_UNAVAILABLE — 검수 서버에 연결하지 못했어요")
  AdminReviewDecisionResponse approve(
      @Parameter(description = "혜택 검수 ID") UUID id,
      AdminReviewDecisionRequest request,
      @Parameter(hidden = true) Principal principal);

  @Operation(
      summary = "혜택 검수 반려",
      description =
          "본문은 비워도 돼요. relevant=false로 다시 내보내 서비스에 안 보이게 해요. 사용자 알림은 보내지 않아요. "
              + "reason(반려 사유)이 있으면 메모 앞에 [사유]로 붙여 남기고, 반려에서는 edits를 무시해요. "
              + "처리 기록의 검수자는 로그인 계정 ID예요. 응답의 pendingCount는 처리 뒤 남은 혜택 검수 대기 건수예요.")
  @ApiResponse(responseCode = "200", description = "처리 결과")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — 본문이 올바르지 않아요 (reason은 정해진 값, note는 500자까지, edits는 200칸까지, "
              + "path는 비우지 않고 300자까지)")
  @ApiResponse(responseCode = "404", description = "NOTICE_REVIEW_NOT_FOUND — 없는 혜택 검수 항목이에요")
  @ApiResponse(
      responseCode = "409",
      description = "NOTICE_REVIEW_CONFLICT — 이미 처리됐거나 더 새 버전 결과가 나간 검수 항목이에요")
  @ApiResponse(responseCode = "503", description = "NOTICE_REVIEW_UNAVAILABLE — 검수 서버에 연결하지 못했어요")
  AdminReviewDecisionResponse reject(
      @Parameter(description = "혜택 검수 ID") UUID id,
      AdminReviewDecisionRequest request,
      @Parameter(hidden = true) Principal principal);
}
