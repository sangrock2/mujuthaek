package kr.mujuthaek.api.traffic.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import kr.mujuthaek.api.traffic.dto.BotTrafficResponse;
import kr.mujuthaek.api.traffic.dto.RealtimeResponse;
import kr.mujuthaek.api.traffic.dto.TrafficResponse;

@Tag(
    name = "관리자 트래픽",
    description =
        "관리자 「트래픽」 화면이에요. 방문·유입·이용 흐름은 Google Analytics(GA)에서, 봇·보안 숫자는 api 서버 요청 기록에서 가져와요. "
            + "권한 TRAFFIC(「트래픽 보기」)이 있는 관리자만 부를 수 있어요.")
public interface AdminTrafficApiSpec {

  @Operation(
      summary = "트래픽 개요",
      description =
          "개요·유입·이용 흐름(GA)과 서버 숫자(가입·로그인·사람/봇 요청)를 줘요. "
              + "GA 숫자는 기간별로 한 시간, 서버 숫자는 1분이 지난 뒤 부르면 지난 값을 먼저 주고 뒤에서 새로 가져와요. "
              + "그래서 서버 숫자는 마지막으로 센 지 최대 10분 된 값이 나올 수 있고, GA 숫자가 언제 값인지는 ga.fetchedAt으로 봐요. "
              + "GA가 연결되지 않았거나 가져오지 못하면 ga.connected가 false이고 ga.error에 이유가 와요(가져오지 못해도 전에 가져온 값이 있으면 그 값을 connected=true 그대로 줘요).")
  TrafficResponse traffic(
      @Parameter(description = "오늘 포함 최근 며칠 (기본 7, 1~90 밖이면 가까운 끝값으로 맞춰요)", example = "7")
          int days);

  @Operation(
      summary = "지금 접속자",
      description =
          "GA 실시간 보고서의 최근 30분·5분 활성 사용자와 최근 30분 기기별 활성 사용자예요. "
              + "30초가 지난 뒤 부르면 지난 값을 먼저 주고 뒤에서 새로 가져와요. 언제 값인지는 fetchedAt으로 봐요. "
              + "GA가 연결되지 않았거나 가져오지 못하면 connected가 false이고 error에 이유가 와요(가져오지 못해도 전에 가져온 값이 있으면 그 값을 connected=true 그대로 줘요).")
  RealtimeResponse realtime();

  @Operation(
      summary = "봇·보안",
      description =
          "api 서버 요청 기록으로 센 숫자예요: 날짜·보낸 쪽별 요청 수, 요청 많은 곳 20곳(가린 IP), 사람이 아닌 요청이 많이 온 경로 15개, "
              + "거절·오류 응답 수(401·403·404·429·5xx), 최근 관리자 API 요청 50건, 최근 로그인 실패 30건. "
              + "같은 days는 1분이 지난 뒤 부르면 지난 값을 먼저 주고 뒤에서 새로 세요. 그래서 마지막으로 센 지 최대 10분 된 값이 나올 수 있어요.")
  BotTrafficResponse bots(
      @Parameter(description = "오늘 포함 최근 며칠 (기본 7, 1~30 밖이면 가까운 끝값으로 맞춰요)", example = "7")
          int days);
}
