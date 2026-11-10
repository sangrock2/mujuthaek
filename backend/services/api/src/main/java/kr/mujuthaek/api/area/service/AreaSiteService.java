package kr.mujuthaek.api.area.service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.area.domain.AreaCriteria;
import kr.mujuthaek.api.area.domain.AreaMetric;
import kr.mujuthaek.api.area.domain.AreaTag;
import kr.mujuthaek.api.area.domain.GeocodeResult.Status;
import kr.mujuthaek.api.area.domain.LifeCategory;
import kr.mujuthaek.api.area.domain.NearestStation;
import kr.mujuthaek.api.area.domain.SiteDetail;
import kr.mujuthaek.api.area.domain.StoredLocation;
import kr.mujuthaek.api.area.domain.WalkMinutes;
import kr.mujuthaek.api.area.repository.PostgresLocationScores;
import kr.mujuthaek.api.area.repository.PostgresNoticeLocations;
import kr.mujuthaek.api.area.repository.PostgresSiteDetails;
import org.springframework.stereotype.Service;

/** 위치 하나의 생활권 정보와 점수 기준표 (8단계 조회 API). 미리 계산해 둔 값만 읽어요. */
@Service
public class AreaSiteService {

  static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");

  private final PostgresNoticeLocations locations;
  private final PostgresSiteDetails details;
  private final PostgresLocationScores scores;
  private final LifeScoreService lifeScores;

  public AreaSiteService(
      PostgresNoticeLocations locations,
      PostgresSiteDetails details,
      PostgresLocationScores scores,
      LifeScoreService lifeScores) {
    this.locations = locations;
    this.details = details;
    this.scores = scores;
    this.lifeScores = lifeScores;
  }

  /** 없는 위치·좌표를 못 찾은 위치면 빈 값. */
  public Optional<SiteDetail> site(UUID siteId) {
    Optional<StoredLocation> found =
        locations.byIds(List.of(siteId)).stream().filter(l -> l.coordinate() != null).findFirst();
    if (found.isEmpty()) {
      return Optional.empty();
    }
    StoredLocation l = found.get();
    PostgresSiteDetails.Metrics m = details.metrics(siteId);
    NearestStation station =
        details
            .nearestStation(siteId)
            .map(
                s ->
                    new NearestStation(
                        s.name(), s.meters(), WalkMinutes.of(BigDecimal.valueOf(s.meters()))))
            .orElse(null);
    Map<LifeCategory, Integer> categories = new EnumMap<>(LifeCategory.class);
    var life = scores.lifeScores(List.of(siteId)).get(siteId);
    if (life != null) {
      life.scores()
          .forEach(
              (c, v) -> categories.put(c, v.setScale(0, RoundingMode.HALF_UP).intValueExact()));
    }
    return Optional.of(
        new SiteDetail(
            siteId,
            l.coordinate().lat(),
            l.coordinate().lng(),
            l.status() == Status.APPROX,
            metrics(m.values(), station),
            categories,
            AreaTag.of(m.values()).stream().sorted().toList(),
            m.calculatedAt() == null ? null : OffsetDateTime.ofInstant(m.calculatedAt(), SEOUL)));
  }

  public AreaCriteria criteria() {
    String version = lifeScores.scoreVersion();
    return new AreaCriteria(
        version,
        details.rules(version).stream()
            .map(r -> new AreaCriteria.Rule(r.metric(), r.xs(), r.ys()))
            .toList(),
        details.lifeWeights(version).stream()
            .map(w -> new AreaCriteria.Weight(w.category(), w.metric(), w.weight()))
            .toList(),
        AreaCriteria.SOURCES);
  }

  private static SiteDetail.Metrics metrics(Map<AreaMetric, BigDecimal> v, NearestStation station) {
    return new SiteDetail.Metrics(
        station,
        count(v, AreaMetric.STATION_COUNT_1KM),
        meters(v, AreaMetric.BUS_STOP_NEAREST_M),
        count(v, AreaMetric.BUS_STOP_COUNT_300M),
        meters(v, AreaMetric.ELEMENTARY_NEAREST_M),
        count(v, AreaMetric.MIDDLE_COUNT_1KM),
        count(v, AreaMetric.HIGH_COUNT_1KM),
        meters(v, AreaMetric.PARK_NEAREST_M),
        count(v, AreaMetric.PARK_AREA_1KM_M2),
        meters(v, AreaMetric.HOSPITAL_NEAREST_M),
        count(v, AreaMetric.CLINIC_COUNT_500M),
        count(v, AreaMetric.CONVENIENCE_STORE_COUNT_300M),
        meters(v, AreaMetric.MART_NEAREST_M),
        count(v, AreaMetric.STORE_COUNT_300M));
  }

  /** 가장 가까운 거리: 근처에 없으면 null. */
  private static Long meters(Map<AreaMetric, BigDecimal> v, AreaMetric metric) {
    BigDecimal value = v.get(metric);
    return value == null ? null : value.setScale(0, RoundingMode.HALF_UP).longValueExact();
  }

  /** 개수·넓이: 근처에 없으면 0. */
  private static long count(Map<AreaMetric, BigDecimal> v, AreaMetric metric) {
    BigDecimal value = v.get(metric);
    return value == null ? 0 : value.setScale(0, RoundingMode.HALF_UP).longValueExact();
  }
}
