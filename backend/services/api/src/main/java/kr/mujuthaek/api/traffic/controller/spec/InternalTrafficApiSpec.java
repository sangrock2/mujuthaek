package kr.mujuthaek.api.traffic.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import kr.mujuthaek.api.traffic.dto.TrafficPageRequest;
import org.springframework.http.ResponseEntity;

@Tag(
    name = "내부 트래픽 수집",
    description =
        "프론트 서버(Next.js proxy)가 사람·봇의 화면 요청을 한 건씩 넘기는 곳이에요. 넘긴 요청은 api 요청과 같은 요청 기록에 「화면(PAGE)」으로 쌓여, "
            + "관리자 트래픽 화면의 사람·봇 요청 수와 방문자 수에 함께 들어가요. 화면만 긁어 가는 봇은 api를 부르지 않아서 이 기록으로만 잡혀요. "
            + "로그인 대신 비밀 헤더 X-Traffic-Token이 맞을 때만 받아요.")
public interface InternalTrafficApiSpec {

  @Operation(
      summary = "화면 요청 넘기기",
      description =
          "화면 요청 한 건을 요청 기록에 「화면(PAGE)」으로 쌓아요. path는 /로 시작해야 하고, ?·# 뒤는 버리고 경로의 ID(UUID·숫자)는 {id}로 묶어 저장해요. "
              + "userAgent로 보낸 쪽(사람·봇 등)을 나누고 200자까지만 저장해요. ip는 IPv4·IPv6 글자가 아니면 버려요. "
              + "서버에 비밀 값(TRAFFIC_INGEST_TOKEN)을 넣지 않았으면 헤더와 상관없이 이 주소는 없는 것처럼 404예요. 아래 400·403·404는 본문이 없어요. "
              + "단, 본문이 없거나 JSON이 아니면 이 검사들보다 먼저 400 VALIDATION_FAILED가 Problem 본문과 함께 와요.")
  @ApiResponse(responseCode = "202", description = "받았어요")
  @ApiResponse(responseCode = "400", description = "path가 없거나 /로 시작하지 않아요")
  @ApiResponse(responseCode = "403", description = "X-Traffic-Token이 없거나 맞지 않아요")
  @ApiResponse(responseCode = "404", description = "서버에 TRAFFIC_INGEST_TOKEN이 없어서 받지 않아요")
  ResponseEntity<Void> page(
      @Parameter(description = "프론트 서버와 나눠 가진 비밀 값. 서버의 TRAFFIC_INGEST_TOKEN과 같아야 해요") String token,
      TrafficPageRequest page);
}
