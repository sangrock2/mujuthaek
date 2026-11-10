package kr.mujuthaek.api.notice.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import tools.jackson.databind.JsonNode;

@Tag(
    name = "관리자 추출 비용·품질",
    description =
        "공고 추출의 비용과 품질(검수 없이 게시된 비율, 담당별 비용, 멈춤)을 기간별로 봐요. 추출 서비스 집계를 이 서버가 대신 불러요. "
            + "「추출 과정 보기」와 같이 권한 NOTICE_REVIEW가 있는 관리자만 부를 수 있어요.")
public interface AdminExtractionStatsApiSpec {

  @Operation(
      summary = "추출 비용·품질 집계",
      description =
          "한국 시간 오늘을 넣어 최근 days일의 집계를 줘요(추출 서비스 응답 그대로). 공고(notices)는 원본·버전 하나이고 상태는 기간의 마지막 작업으로, "
              + "비용은 다시 처리한 작업까지 더해요(cost_usd, 예산 기준 추정 달러). statuses.groups는 자동 게시·부분 게시·검수로 감·실패·그 밖의 "
              + "공고 수와 비율, publishedWithoutReviewRatio는 자동·부분 게시 비율이에요. costPerNotice는 공고당 평균·최대 비용, daily는 하루별 "
              + "작업·공고 수와 비용, topJobs는 비용이 큰 작업(jobId로 「추출 과정 보기」). usage는 작업 기록에서 모은 담당별 비용 비중(byAgent), "
              + "캐시 읽기 비율(cachedRatio), 끝내기 전 멈춤(stops: 호출 상한·예산 상한·출력 한도·오류), 넣기 거절(addRejections), "
              + "해결 담당 실행·채택(resolver)이에요. 작업이 많으면 최근 작업 limit개만 보고 truncated가 true예요.")
  @ApiResponse(responseCode = "200", description = "추출 비용·품질 집계")
  @ApiResponse(responseCode = "503", description = "NOTICE_REVIEW_UNAVAILABLE — 검수 서버에 연결하지 못했어요")
  JsonNode stats(
      @Parameter(
              description = "최근 며칠 (기본 30, 1~90 밖이면 가까운 끝값으로 맞춰요. 응답의 days가 실제로 쓴 값)",
              example = "30")
          int days);
}
