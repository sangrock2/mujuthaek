package kr.mujuthaek.api.notice.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.security.Principal;
import java.util.UUID;
import kr.mujuthaek.api.notice.dto.request.GeneralReportRequest;
import kr.mujuthaek.api.notice.dto.request.NoticeReportRequest;
import kr.mujuthaek.api.notice.dto.response.NoticeReportCreatedResponse;

@Tag(
    name = "제보 보내기",
    description =
        "회원이 공고·창업지원 사업·주거·복지 정책(혜택)의 틀린 값이나, 대상 없는 일반 제보를 보내요. "
            + "로그인한 회원만 보낼 수 있고, 한 회원이 하루(한국 시간)에 모두 합쳐 20건까지예요.")
public interface NoticeReportApiSpec {

  @Operation(
      summary = "창업지원 사업 제보",
      description =
          "창업지원 사업·사업공간 모집의 틀린 값을 알려요. id는 판정 API의 programId(rawPolicyId)이고, 판정 틀이 있는 사업에만 받아요. "
              + "reportedValue(맞다고 생각하는 값)나 note(설명) 중 하나는 꼭 적어요.")
  @ApiResponse(responseCode = "200", description = "받은 제보 (status는 NEW)")
  @ApiResponse(
      responseCode = "400",
      description = "VALIDATION_FAILED — field가 비었거나 칸 길이를 넘었어요. reportedValue와 note가 둘 다 비었어요")
  @ApiResponse(responseCode = "401", description = "UNAUTHENTICATED — 로그인하지 않았어요")
  @ApiResponse(responseCode = "404", description = "NOT_FOUND — 판정 틀이 있는 창업지원 사업·사업공간 모집이 아니에요")
  @ApiResponse(responseCode = "409", description = "CONFLICT — 같은 칸에 보낸 제보가 아직 처리 전이에요")
  @ApiResponse(responseCode = "429", description = "RATE_LIMITED — 오늘 보낸 제보가 20건이에요")
  NoticeReportCreatedResponse reportProgram(
      @Parameter(description = "창업지원 사업 ID (rawPolicyId)") UUID id,
      NoticeReportRequest request,
      @Parameter(hidden = true) Principal principal);

  @Operation(
      summary = "혜택 제보",
      description =
          "주거·복지 정책(혜택)의 틀린 값을 알려요. id는 정책 원본 ID(policy.extracted의 rawPolicyId)이고, 혜택 ID를 주면 원본 ID로 바꿔요. "
              + "이 서버의 혜택이나 추출 서비스의 정제 결과에 있는 정책에만 받아요. "
              + "reportedValue(맞다고 생각하는 값)나 note(설명) 중 하나는 꼭 적어요.")
  @ApiResponse(responseCode = "200", description = "받은 제보 (status는 NEW)")
  @ApiResponse(
      responseCode = "400",
      description = "VALIDATION_FAILED — field가 비었거나 칸 길이를 넘었어요. reportedValue와 note가 둘 다 비었어요")
  @ApiResponse(responseCode = "401", description = "UNAUTHENTICATED — 로그인하지 않았어요")
  @ApiResponse(
      responseCode = "404",
      description = "NOT_FOUND — 이 서버의 혜택에도, 추출 서비스의 정제 결과에도 없는 정책이에요")
  @ApiResponse(responseCode = "409", description = "CONFLICT — 같은 칸에 보낸 제보가 아직 처리 전이에요")
  @ApiResponse(responseCode = "429", description = "RATE_LIMITED — 오늘 보낸 제보가 20건이에요")
  @ApiResponse(
      responseCode = "503",
      description = "NOTICE_REVIEW_UNAVAILABLE — 이 서버에 없는 정책이라 추출 서비스에 물었는데 연결하지 못했어요")
  NoticeReportCreatedResponse reportBenefit(
      @Parameter(description = "정책 원본 ID (rawPolicyId) 또는 혜택 ID") UUID id,
      NoticeReportRequest request,
      @Parameter(hidden = true) Principal principal);

  @Operation(
      summary = "일반 제보",
      description =
          "공고·혜택·사업에 묶이지 않은 제보예요. field는 MISSING_NOTICE(빠진 공고·정책) · WRONG_INFO(틀린 정보) · "
              + "APP_ERROR(화면 오류) · ETC(기타) 중 하나이고, note는 꼭 적어요. 같은 종류끼리 묶지 않아요.")
  @ApiResponse(responseCode = "200", description = "받은 제보 (status는 NEW)")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — field가 MISSING_NOTICE·WRONG_INFO·APP_ERROR·ETC가 아니에요. note가 비었거나 칸 길이를 넘었어요")
  @ApiResponse(responseCode = "401", description = "UNAUTHENTICATED — 로그인하지 않았어요")
  @ApiResponse(responseCode = "429", description = "RATE_LIMITED — 오늘 보낸 제보가 20건이에요")
  NoticeReportCreatedResponse reportGeneral(
      GeneralReportRequest request, @Parameter(hidden = true) Principal principal);

  @Operation(
      summary = "공고 제보",
      description =
          "공고의 틀린 값을 알려요. 공개된 공고에만 받아요. reportedValue(맞다고 생각하는 값)나 note(설명) 중 하나는 꼭 적어요. "
              + "예: {\"field\":\"보증금\",\"currentValue\":\"2,400만 원\",\"reportedValue\":\"2,600만 원\",\"note\":\"공고문 4쪽\"}")
  @ApiResponse(responseCode = "200", description = "받은 제보 (status는 NEW)")
  @ApiResponse(
      responseCode = "400",
      description = "VALIDATION_FAILED — field가 비었거나 칸 길이를 넘었어요. reportedValue와 note가 둘 다 비었어요")
  @ApiResponse(responseCode = "401", description = "UNAUTHENTICATED — 로그인하지 않았어요")
  @ApiResponse(responseCode = "404", description = "NOTICE_NOT_FOUND — 공고가 없거나 숨김·공개 전이에요")
  @ApiResponse(responseCode = "409", description = "CONFLICT — 같은 칸에 보낸 제보가 아직 처리 전이에요")
  @ApiResponse(responseCode = "429", description = "RATE_LIMITED — 오늘 보낸 제보가 20건이에요")
  NoticeReportCreatedResponse report(
      @Parameter(description = "공고 ID") UUID id,
      NoticeReportRequest request,
      @Parameter(hidden = true) Principal principal);
}
