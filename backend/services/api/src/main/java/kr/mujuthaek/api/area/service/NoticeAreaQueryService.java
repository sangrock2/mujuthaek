package kr.mujuthaek.api.area.service;

import java.math.BigDecimal;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;
import kr.mujuthaek.api.area.domain.AreaTag;
import kr.mujuthaek.api.area.domain.GeocodeResult.Status;
import kr.mujuthaek.api.area.domain.LifeCategory;
import kr.mujuthaek.api.area.domain.StoredLocation;
import kr.mujuthaek.api.area.domain.TotalScore;
import kr.mujuthaek.api.area.repository.PostgresLocationScores;
import kr.mujuthaek.api.area.repository.PostgresNoticeLocations;
import kr.mujuthaek.api.area.repository.PostgresSiteDetails;
import org.springframework.stereotype.Service;

/**
 * notice가 공고 목록·상세·지도에 붙일 area 값 (8단계 46번). notice는 area 표를 직접 읽지 않고 이 조회 메서드를 불러요(모듈 규칙). 미리 계산해 둔
 * 값만 읽어요.
 */
@Service
public class NoticeAreaQueryService {

  /**
   * 공고 위치 하나의 area 값.
   *
   * @param noticeLocationId 공고 상세 sites[].id (예: building-a)
   * @param siteId area 위치 ID (GET /areas/sites/{siteId})
   * @param lat 좌표를 못 찾았으면 null
   * @param approximate 법정동 대표점(대략 위치)이면 true
   * @param tags 세권 태그 코드 (STATION, SCHOOL, ELEMENTARY_NEAR, PARK, CONVENIENCE, CLINIC)
   * @param livingScore 생활권 총점 0~100 (항목 5개 같은 비중, 점수가 없으면 null)
   */
  public record NoticeSite(
      String noticeLocationId,
      UUID siteId,
      Double lat,
      Double lng,
      boolean approximate,
      List<String> tags,
      Integer livingScore) {}

  /** 지도에 찍을 공고 대표 좌표. */
  public record NoticePoint(UUID noticeId, double lat, double lng) {}

  private final PostgresNoticeLocations locations;
  private final PostgresSiteDetails details;
  private final PostgresLocationScores scores;

  public NoticeAreaQueryService(
      PostgresNoticeLocations locations,
      PostgresSiteDetails details,
      PostgresLocationScores scores) {
    this.locations = locations;
    this.details = details;
    this.scores = scores;
  }

  /** 공고 ID → 위치들 (notice 위치 ID 순). area가 아직 모르는 공고는 빠져요. */
  public Map<UUID, List<NoticeSite>> sitesOf(Collection<UUID> noticeIds) {
    List<StoredLocation> stored = locations.ofNotices(noticeIds);
    List<UUID> ids = stored.stream().map(StoredLocation::locationId).toList();
    var metrics = details.metricsOf(ids);
    var life = scores.lifeScores(ids);
    return stored.stream()
        .collect(
            Collectors.groupingBy(
                StoredLocation::noticeId,
                LinkedHashMap::new,
                Collectors.mapping(
                    l -> {
                      Map<LifeCategory, BigDecimal> s =
                          life.containsKey(l.locationId())
                              ? life.get(l.locationId()).scores()
                              : Map.of();
                      return new NoticeSite(
                          l.noticeLocationId(),
                          l.locationId(),
                          l.coordinate() == null ? null : l.coordinate().lat(),
                          l.coordinate() == null ? null : l.coordinate().lng(),
                          l.status() == Status.APPROX,
                          l.coordinate() == null
                              ? List.of()
                              : AreaTag.of(metrics.getOrDefault(l.locationId(), Map.of())).stream()
                                  .sorted()
                                  .map(Enum::name)
                                  .toList(),
                          s.isEmpty() ? null : TotalScore.of(s, Map.of()));
                    },
                    Collectors.toList())));
  }

  /** 지도 범위 안 공고의 대표 좌표 (공고마다 하나, 최대 limit개). */
  public List<NoticePoint> pointsWithin(
      double swLat, double swLng, double neLat, double neLng, int limit) {
    return locations.representativesWithin(swLat, swLng, neLat, neLng, limit).stream()
        .map(l -> new NoticePoint(l.noticeId(), l.coordinate().lat(), l.coordinate().lng()))
        .toList();
  }
}
