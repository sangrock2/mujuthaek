package kr.mujuthaek.api.area.domain;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * 위치 하나의 생활권 정보 (GET /areas/sites/{siteId}): 좌표, 세권 지표, 생활권 항목 점수, 세권 태그.
 *
 * @param siteId area 위치 ID
 * @param approximate 대략 위치(법정동 대표점)면 true — 지표·점수도 그 점 기준이에요
 * @param tags 세권 태그 ({@link AreaTag} 코드)
 * @param calculatedAt 지표를 마지막으로 계산한 시각 (서울 시간, 아직 없으면 null)
 */
public record SiteDetail(
    UUID siteId,
    double lat,
    double lng,
    boolean approximate,
    Metrics metrics,
    @Schema(
            example =
                "{\"TRANSIT\": 85, \"SCHOOL\": 70, \"PARK\": 90, \"CONVENIENCE\": 60, \"HOSPITAL\": 55}")
        Map<LifeCategory, Integer> categoryScores,
    List<AreaTag> tags,
    OffsetDateTime calculatedAt) {

  /**
   * 세권 지표. 거리는 직선 m, 수는 반경 안 개수. 근처에 그 시설이 아예 없으면 null(가장 가까운 거리) 또는 0(개수).
   *
   * @param nearestStation 가장 가까운 도시철도역 이름·거리·도보 분
   * @param stationCount1km 1km 안 역 수 (환승역 하나 = 1)
   * @param hospitalNearestM 가장 가까운 2차 이상 병원
   * @param clinics500m 500m 안 동네 의원
   * @param martNearestM 가장 가까운 슈퍼마켓
   */
  public record Metrics(
      NearestStation nearestStation,
      long stationCount1km,
      Long busStopNearestM,
      long busStops300m,
      Long elementaryNearestM,
      long middleSchools1km,
      long highSchools1km,
      Long parkNearestM,
      long parkArea1kmM2,
      Long hospitalNearestM,
      long clinics500m,
      long convenienceStores300m,
      Long martNearestM,
      long stores300m) {}
}
