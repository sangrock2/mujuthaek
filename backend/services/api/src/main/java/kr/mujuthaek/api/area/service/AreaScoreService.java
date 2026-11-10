package kr.mujuthaek.api.area.service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.api.area.domain.Coordinate;
import kr.mujuthaek.api.area.domain.LifeCategory;
import kr.mujuthaek.api.area.domain.Piecewise;
import kr.mujuthaek.api.area.domain.SiteScore;
import kr.mujuthaek.api.area.domain.StoredLocation;
import kr.mujuthaek.api.area.domain.TotalScore;
import kr.mujuthaek.api.area.repository.PostgresLocationScores;
import kr.mujuthaek.api.area.repository.PostgresNoticeLocations;
import kr.mujuthaek.api.area.repository.PostgresScoreRules;
import org.springframework.stereotype.Service;

/**
 * 요청 때 계산하는 생활권 총점과 통근 (5단계, API 문서 POST /areas/score). 사용자 가중치와 직장 위치가 들어가서 저장하지 않고 로그에도 남기지 않아요.
 *
 * <ul>
 *   <li>항목 점수: 저장된 생활권 항목 점수(6단계)
 *   <li>직장: 직장 위치에서 위치까지 직선거리(PostGIS 타원체 거리)를 점수 규칙 {@code work_distance_m}(3km 100 → 7km 80 →
 *       15km 60 → 25km 30 → 40km 0)으로. 길찾기 API(ODsay 등)는 쓰지 않아서 통근 시간은 null이에요
 *   <li>총점: Σ(점수 × 가중치) ÷ 가중치 합, 0.5 올림({@link TotalScore}). 가중치가 모두 0이면 같은 비중
 * </ul>
 */
@Service
public class AreaScoreService {

  static final String WORK_RULE = "work_distance_m";
  static final int MAX_WEIGHT = 10;

  private final PostgresNoticeLocations locations;
  private final PostgresLocationScores scores;
  private final PostgresScoreRules rules;
  private final LifeScoreService lifeScores;

  public AreaScoreService(
      PostgresNoticeLocations locations,
      PostgresLocationScores scores,
      PostgresScoreRules rules,
      LifeScoreService lifeScores) {
    this.locations = locations;
    this.scores = scores;
    this.rules = rules;
    this.lifeScores = lifeScores;
  }

  /**
   * 위치마다 총점·항목 점수·통근 거리. 받은 순서대로이고, 없는 위치는 빠져요(API가 404·무시를 정해요).
   *
   * @param priorities 항목별 가중치 0~10 (없는 항목은 0)
   * @param workplace 직장 위치 (없으면 직장 항목 없이)
   */
  public List<SiteScore> score(
      List<UUID> siteIds, Map<LifeCategory, Integer> priorities, Coordinate workplace) {
    priorities.forEach(
        (category, weight) -> {
          if (weight == null || weight < 0 || weight > MAX_WEIGHT) {
            throw new IllegalArgumentException("가중치는 0~" + MAX_WEIGHT + "이어야 해요: " + category);
          }
        });
    List<UUID> ids = new ArrayList<>(new LinkedHashSet<>(siteIds));
    Map<UUID, StoredLocation> found = new java.util.HashMap<>();
    locations.byIds(ids).forEach(l -> found.put(l.locationId(), l));
    var life = scores.lifeScores(found.keySet());
    Map<UUID, Long> distances =
        workplace == null ? Map.of() : locations.distancesFrom(found.keySet(), workplace);
    Piecewise work =
        workplace == null
            ? null
            : rules
                .rule(lifeScores.scoreVersion(), WORK_RULE)
                .orElseThrow(
                    () ->
                        new IllegalStateException(
                            "직장 거리 점수 규칙이 없어요: " + lifeScores.scoreVersion()));

    List<SiteScore> out = new ArrayList<>();
    for (UUID id : ids) {
      if (!found.containsKey(id)) {
        continue;
      }
      Map<LifeCategory, BigDecimal> forTotal = new EnumMap<>(LifeCategory.class);
      var stored = life.get(id);
      if (stored != null) {
        forTotal.putAll(stored.scores());
      }
      Long meters = distances.get(id);
      if (work != null && meters != null) {
        forTotal.put(LifeCategory.WORK, work.apply(BigDecimal.valueOf(meters)));
      }
      Map<LifeCategory, Integer> shown = new EnumMap<>(LifeCategory.class);
      forTotal.forEach((c, v) -> shown.put(c, v.setScale(0, RoundingMode.HALF_UP).intValueExact()));
      out.add(
          new SiteScore(
              id,
              forTotal.isEmpty() ? null : TotalScore.of(forTotal, priorities),
              Collections.unmodifiableMap(shown),
              meters,
              null));
    }
    return out;
  }
}
