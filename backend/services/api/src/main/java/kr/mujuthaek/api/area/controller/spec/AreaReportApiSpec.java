package kr.mujuthaek.api.area.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.security.Principal;
import java.util.UUID;
import kr.mujuthaek.api.area.dto.request.AreaReportRequest;
import kr.mujuthaek.api.area.dto.request.AreaReportResolveRequest;
import kr.mujuthaek.api.area.dto.response.AreaReportResponse;

@Tag(
    name = "생활권 제보",
    description =
        "회원이 공고의 생활권 값이 다르다고 알리고, 관리자가 처리해 답을 남겨요. 제보 보내기는 로그인한 회원, "
            + "/api/admin/area-reports는 권한 REPORTS가 있는 관리자만 불러요. 제보한 회원이 누구인지는 응답에 넣지 않아요.")
public interface AreaReportApiSpec {

  @Operation(
      summary = "생활권 제보 보내기 (회원)",
      description =
          "회원이 공고의 생활권 값(역까지 거리 등)이 다르다고 알려요. 로그인한 회원만, 생활권 위치를 계산한 공고에만 보낼 수 있어요. "
              + "맞는 값(reportedValue)이나 설명(note) 중 하나는 있어야 해요. 단지가 여럿인 공고면 noticeLocationId에 공고 상세 locations[].id를 넣어요. "
              + "하루(서울 시간)에 20건까지 보낼 수 있고, 같은 공고·항목에 보낸 제보가 아직 끝나지 않았으면(NEW·DOING) 다시 보낼 수 없어요.")
  @ApiResponse(responseCode = "200", description = "받은 제보 (status NEW)")
  @ApiResponse(
      responseCode = "400",
      description = "VALIDATION_FAILED — field가 비었거나, 글자 수 제한을 넘거나, reportedValue·note가 둘 다 비었어요")
  @ApiResponse(responseCode = "401", description = "UNAUTHENTICATED — 로그인하지 않았어요")
  @ApiResponse(responseCode = "404", description = "NOT_FOUND — 생활권 정보가 있는 공고가 아니에요")
  @ApiResponse(responseCode = "409", description = "CONFLICT — 같은 공고·항목에 보낸 제보를 아직 확인하고 있어요")
  @ApiResponse(responseCode = "429", description = "RATE_LIMITED — 오늘(서울 시간) 이미 20건을 보냈어요")
  AreaReportResponse.Created report(
      @Parameter(description = "공고 ID") UUID id,
      AreaReportRequest request,
      @Parameter(hidden = true) Principal principal);

  @Operation(
      summary = "생활권 제보 목록 (관리자)",
      description = "최근 받은 것부터 100건까지와 상태별 건수를 줘요. summary는 설명(note)의 앞 40자예요.")
  @ApiResponse(responseCode = "200", description = "목록과 건수")
  @ApiResponse(
      responseCode = "400",
      description = "VALIDATION_FAILED — status가 NEW·DOING·DONE이 아니에요")
  AreaReportResponse.ListView list(
      @Parameter(description = "NEW(처리 전) · DOING(처리 중) · DONE(끝남) 중 하나. 비우면 모두", example = "NEW")
          String status);

  @Operation(
      summary = "생활권 제보 상태별 건수 (관리자)",
      description = "NEW·DOING·DONE별 건수(newCount·doing·done)예요.")
  AreaReportResponse.Counts counts();

  @Operation(
      summary = "생활권 제보 상세 (관리자)",
      description = "제보 한 건과, 같은 공고·항목에 온 다른 제보 중 맞는 값이나 설명이 있는 것(notes, 오래된 것부터)을 줘요.")
  @ApiResponse(responseCode = "200", description = "제보 상세")
  @ApiResponse(responseCode = "404", description = "NOT_FOUND — 제보를 찾을 수 없어요")
  AreaReportResponse.Detail detail(@Parameter(description = "제보 ID") UUID id);

  @Operation(
      summary = "생활권 제보 처리 시작 (관리자)",
      description = "처리 전(NEW) 제보를 처리 중(DOING)으로 바꾸고 맡은 관리자를 남겨요. 이미 처리 중이거나 끝난 제보는 그대로 두고 상세를 줘요.")
  @ApiResponse(responseCode = "200", description = "제보 상세")
  @ApiResponse(responseCode = "404", description = "NOT_FOUND — 제보를 찾을 수 없어요")
  AreaReportResponse.Detail start(
      @Parameter(description = "제보 ID") UUID id, @Parameter(hidden = true) Principal principal);

  @Operation(
      summary = "생활권 제보 처리 끝 (관리자)",
      description =
          "result(FIXED 고침 · KEPT 그대로 둠)로 처리를 끝내요. group이 true이거나 없으면 같은 공고·항목의 아직 끝나지 않은(NEW·DOING) 제보도 같이 끝내요. "
              + "reply를 적으면 이번에 끝낸 제보마다 그 회원에게 답장 알림이 가요(비우면 답장 없음). "
              + "FIXED여도 생활권 값을 다시 계산하지는 않아요(처리 기록만 남겨요).")
  @ApiResponse(responseCode = "200", description = "처리한 제보 상세")
  @ApiResponse(
      responseCode = "400",
      description = "VALIDATION_FAILED — result가 없거나 FIXED·KEPT가 아니거나, reply가 1000자를 넘어요")
  @ApiResponse(responseCode = "404", description = "NOT_FOUND — 제보를 찾을 수 없어요")
  @ApiResponse(responseCode = "409", description = "CONFLICT — 이미 처리한 제보예요")
  AreaReportResponse.Detail resolve(
      @Parameter(description = "제보 ID") UUID id,
      AreaReportResolveRequest request,
      @Parameter(hidden = true) Principal principal);
}
