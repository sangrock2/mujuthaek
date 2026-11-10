package kr.mujuthaek.api.common.event;

import java.util.List;
import java.util.UUID;

/**
 * 공고의 위치가 정해지거나 바뀜 (초안: area 담당과 확정 전). area가 받아 위치별 생활·상업 점수를 계산하고 AreaScoresCalculated로 돌려줘요.
 * area는 다른 모듈을 조회하지 않으므로 계산에 필요한 위치 정보를 여기에 모두 담아요.
 *
 * @param noticeVersion 이 위치를 담은 공고 버전
 */
public record NoticeLocationsChanged(UUID noticeId, int noticeVersion, List<Location> locations) {

  /**
   * 위치 하나 (표준 공고 locations[]).
   *
   * @param locationId 공고 안에서 위치를 가리키는 ID (점수를 돌려줄 때 그대로 써요)
   * @param kind COMPLEX, BUILDING, SITE, UNKNOWN
   * @param regionCode 법정동코드 10자리 (모르면 null)
   * @param address 원문 주소 (모르면 null)
   * @param name 단지·건물 이름 (모르면 null)
   */
  public record Location(
      String locationId, String kind, String regionCode, String address, String name) {}
}
