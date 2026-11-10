package kr.mujuthaek.api.notice.service.internal;

import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.notice.client.ExtractionReviewClient;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;

/**
 * 관리자 「추출 비용·품질」: 추출 서비스 집계(/stats/extraction)를 그대로 넘겨요. 지표 이름·담당 이름이 추출 서비스 안의 것이라 여기서 모양을 다시 정하면
 * 두 곳을 고쳐야 해서요(「추출 과정 보기」와 같은 방식). 공고 원문 제목·비용·토큰만 있고 사용자 정보는 없어요.
 */
@Service
public class AdminExtractionStatsService {

  static final int MAX_DAYS = 90;

  private final ExtractionReviewClient client;

  public AdminExtractionStatsService(ExtractionReviewClient client) {
    this.client = client;
  }

  /** 최근 days일(1~90 밖이면 가까운 끝값). */
  public JsonNode stats(int days) {
    JsonNode body = client.extractionStats(Math.clamp(days, 1, MAX_DAYS));
    if (body == null || body.isNull()) {
      throw new CustomException(ErrorCode.NOTICE_REVIEW_UNAVAILABLE);
    }
    return body;
  }
}
