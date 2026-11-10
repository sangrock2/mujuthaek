package kr.mujuthaek.api.notice.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import tools.jackson.databind.JsonNode;

@Tag(
    name = "관리자 수집 출처",
    description =
        "출처별 수집 상태를 보고 멈추기·다시 켜기·지금 수집을 해요. 수집기 관리자 API를 이 서버가 대신 부르고 응답은 수집기 JSON 그대로예요. "
            + "권한 SOURCES가 있는 관리자만 부를 수 있어요.")
public interface AdminSourceApiSpec {

  @Operation(
      summary = "출처별 수집 상태",
      description =
          "asOf, summary(정상 ok · 지연 late · 실패 fail · 멈춤 paused 출처 수), sources(출처마다 code · name · enabled · "
              + "state · 마지막 회차 lastRun · 마지막 성공 lastSuccessAt · 연속 0건 consecutiveEmpty · 연속 실패 "
              + "consecutiveFailures · 누적 수집 수 totalCollected · 최근 회차 10개 recentRuns)를 줘요. "
              + "지연은 켜진 출처가 26시간 넘게 성공한 회차가 없을 때예요.")
  @ApiResponse(responseCode = "200", description = "수집 상태")
  @ApiResponse(responseCode = "503", description = "NOTICE_COLLECTOR_UNAVAILABLE — 수집기에 연결하지 못했어요")
  JsonNode sources();

  @Operation(
      summary = "출처 멈춤",
      description = "그 출처를 꺼서 스케줄러가 수집하지 않게 해요. 응답은 {code, enabled: false}예요.")
  @ApiResponse(responseCode = "200", description = "바꾼 상태")
  @ApiResponse(responseCode = "404", description = "NOT_FOUND — 없는 수집 출처예요")
  @ApiResponse(responseCode = "503", description = "NOTICE_COLLECTOR_UNAVAILABLE — 수집기에 연결하지 못했어요")
  JsonNode pause(@Parameter(description = "수집 출처 코드", example = "sh") String code);

  @Operation(
      summary = "지금 한 번 수집",
      description = "수집기가 그 출처를 뒤에서 수집하고 바로 {code, started: true}를 줘요. 결과는 출처별 수집 상태에서 봐요.")
  @ApiResponse(responseCode = "200", description = "수집 시작")
  @ApiResponse(responseCode = "404", description = "NOT_FOUND — 없는 수집 출처예요")
  @ApiResponse(responseCode = "409", description = "CONFLICT — 멈춘 출처이거나 그 출처를 지금 수집 중이에요")
  @ApiResponse(
      responseCode = "503",
      description =
          "NOTICE_COLLECTOR_UNAVAILABLE — 수집기에 연결하지 못했거나, 수집기가 스케줄러 없이 떠 있어 지금 수집을 할 수 없어요")
  JsonNode run(@Parameter(description = "수집 출처 코드", example = "sh") String code);

  @Operation(summary = "출처 다시 켜기", description = "멈춘 출처를 다시 켜요. 응답은 {code, enabled: true}예요.")
  @ApiResponse(responseCode = "200", description = "바꾼 상태")
  @ApiResponse(responseCode = "404", description = "NOT_FOUND — 없는 수집 출처예요")
  @ApiResponse(responseCode = "503", description = "NOTICE_COLLECTOR_UNAVAILABLE — 수집기에 연결하지 못했어요")
  JsonNode resume(@Parameter(description = "수집 출처 코드", example = "sh") String code);
}
