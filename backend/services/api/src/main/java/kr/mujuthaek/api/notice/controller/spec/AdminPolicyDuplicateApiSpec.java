package kr.mujuthaek.api.notice.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.security.Principal;
import java.util.UUID;
import kr.mujuthaek.api.notice.dto.request.AdminPolicyDuplicateDecideRequest;
import kr.mujuthaek.api.notice.dto.response.AdminPolicyDuplicateResponse;

@Tag(
    name = "관리자 사업 중복 의심",
    description =
        "관리자 「제보·신고」의 「중복 의심」이에요. 출처에 두 번 올라온 것 같은 창업 지원·입주 모집 사업을 둘 다 두거나 나중 것을 숨겨요. "
            + "권한 REPORTS가 있는 관리자만 부를 수 있어요.")
public interface AdminPolicyDuplicateApiSpec {

  @Operation(
      summary = "중복 의심 목록",
      description =
          "그 상태의 후보를 최근 것부터 최대 200건 주고, 상태별 건수도 함께 줘요. later가 나중에 들어온 사업, earlier가 먼저 있던 사업이에요.")
  @ApiResponse(responseCode = "200", description = "목록 · 상태별 건수")
  @ApiResponse(
      responseCode = "400",
      description = "VALIDATION_FAILED — status가 PENDING·KEPT_BOTH·HIDDEN 중 하나가 아니에요")
  AdminPolicyDuplicateResponse list(
      @Parameter(description = "후보 상태 PENDING · KEPT_BOTH · HIDDEN. 비우면 PENDING") String status);

  @Operation(summary = "중복 의심 상태별 건수", description = "사이드바 숫자예요.")
  AdminPolicyDuplicateResponse.Counts counts();

  @Operation(
      summary = "중복 의심 처리",
      description =
          "action이 KEEP_BOTH면 둘 다 두고, HIDE_LATER면 나중에 들어온 사업을 숨겨요(열린 목록·판정·알림에서 빠짐). "
              + "처리한 관리자는 로그인 계정 ID로 남아요. 처리하고 상태별 건수(사이드바 숫자)를 돌려줘요.")
  @ApiResponse(responseCode = "200", description = "처리 뒤 상태별 건수")
  @ApiResponse(
      responseCode = "400",
      description = "VALIDATION_FAILED — action이 비었거나 KEEP_BOTH·HIDE_LATER 중 하나가 아니에요")
  @ApiResponse(responseCode = "409", description = "CONFLICT — 이미 처리했거나 없는 중복 후보예요")
  AdminPolicyDuplicateResponse.Counts decide(
      @Parameter(description = "나중에 들어온 사업 ID (rawPolicyId)") UUID later,
      @Parameter(description = "먼저 있던 사업 ID (rawPolicyId)") UUID earlier,
      AdminPolicyDuplicateDecideRequest request,
      @Parameter(hidden = true) Principal principal);
}
