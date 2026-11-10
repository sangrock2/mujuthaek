package kr.mujuthaek.api.common.event;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

/**
 * area가 공고 위치의 생활·상업 점수를 계산함 (초안: area 담당과 확정 전). notice가 받아 공고 상세의 areaSummaries로 보여 줘요. 사용자 개인
 * 선호·직장·통근 점수는 넣지 않아요 (공통 점수만).
 *
 * @param noticeVersion 계산에 쓴 위치가 담긴 공고 버전 (NoticeLocationsChanged.noticeVersion)
 */
public record AreaScoresCalculated(UUID noticeId, int noticeVersion, List<Score> scores) {

  /**
   * 위치 하나의 점수.
   *
   * @param kind LIVING(생활) 또는 COMMERCIAL(상업)
   * @param score 0~100
   * @param calculationVersion area 계산 방식 버전
   */
  public record Score(
      String locationId,
      String kind,
      double score,
      Instant calculatedAt,
      String calculationVersion) {}
}
