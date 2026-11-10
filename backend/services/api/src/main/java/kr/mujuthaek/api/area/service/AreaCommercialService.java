package kr.mujuthaek.api.area.service;

import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;
import java.time.Clock;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.area.domain.CommercialIndustry;
import kr.mujuthaek.api.area.domain.CommercialScore;
import kr.mujuthaek.api.area.domain.NearestStation;
import kr.mujuthaek.api.area.domain.Piecewise;
import kr.mujuthaek.api.area.domain.WalkMinutes;
import kr.mujuthaek.api.area.repository.PostgresCommercialMeasures;
import kr.mujuthaek.api.area.repository.PostgresCommercialMeasures.Measures;
import kr.mujuthaek.api.area.repository.PostgresScoreRules;
import org.springframework.stereotype.Service;

/**
 * 공공 상가 위치의 상권 점수 (7단계, 요청 때 계산·저장 안 함). 사용자 업종이 있어야 "같은 업종"을 셀 수 있어서 미리 계산하지 않아요.
 *
 * <ul>
 *   <li>밀도(DENSITY): 300m 안 점포 수
 *   <li>경쟁(COMPETITION): 입지계수 = (300m 안 같은 업종 ÷ 300m 안 전체) ÷ (전국 같은 업종 ÷ 전국 전체). 1보다 크면 과밀이라 낮게. 같은
 *       업종이 없는 업종이거나 300m 안 점포가 0이면 빠져요
 *   <li>교통(TRANSIT): 가장 가까운 도시철도역 거리 (역 자료가 없으면 0점)
 *   <li>총점: 있는 항목의 평균, 0.5 올림
 * </ul>
 *
 * <p>구간은 점수 규칙(area.score_rules)의 commercial_* 이고, 실제 공공 상가 공고로 맞춰 보기 전의 임시 값이에요.
 */
@Service
public class AreaCommercialService {

  static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");
  static final String DENSITY = "DENSITY";
  static final String COMPETITION = "COMPETITION";
  static final String TRANSIT = "TRANSIT";

  private final PostgresCommercialMeasures measures;
  private final PostgresScoreRules rules;
  private final LifeScoreService lifeScores;
  private final Clock clock;

  public AreaCommercialService(
      PostgresCommercialMeasures measures,
      PostgresScoreRules rules,
      LifeScoreService lifeScores,
      Clock clock) {
    this.measures = measures;
    this.rules = rules;
    this.lifeScores = lifeScores;
    this.clock = clock;
  }

  /**
   * @param industryCode 사업 업종 (FOOD·CAFE·RETAIL만 같은 업종이 있어요. 그 밖·없음이면 경쟁 점수 없이)
   * @return 위치가 없거나 좌표가 없으면 빈 값
   */
  public Optional<CommercialScore> score(UUID siteId, String industryCode) {
    CommercialIndustry industry = CommercialIndustry.of(industryCode).orElse(null);
    Optional<Measures> found = measures.measure(siteId, industry);
    if (found.isEmpty()) {
      return Optional.empty();
    }
    Measures m = found.get();
    Map<String, Integer> scores = new LinkedHashMap<>();
    scores.put(DENSITY, rule("commercial_store_count_300m", BigDecimal.valueOf(m.stores300m())));
    BigDecimal quotient = locationQuotient(m);
    if (quotient != null) {
      scores.put(COMPETITION, rule("commercial_location_quotient", quotient));
    }
    scores.put(
        TRANSIT,
        m.stationMeters() == null
            ? 0
            : rule("commercial_station_m", BigDecimal.valueOf(m.stationMeters())));
    int total =
        BigDecimal.valueOf(scores.values().stream().mapToInt(Integer::intValue).sum())
            .divide(BigDecimal.valueOf(scores.size()), 0, RoundingMode.HALF_UP)
            .intValueExact();
    NearestStation station =
        m.stationName() == null
            ? null
            : new NearestStation(
                m.stationName(),
                m.stationMeters(),
                WalkMinutes.of(BigDecimal.valueOf(m.stationMeters())));
    return Optional.of(
        new CommercialScore(
            siteId,
            m.stores300m(),
            industry == null ? null : m.sameIndustry300m(),
            industry,
            station,
            null,
            scores,
            total,
            OffsetDateTime.ofInstant(clock.instant(), SEOUL)));
  }

  /** 입지계수. 업종이 없거나, 300m 안 점포가 0이거나, 전국 비율이 없으면(0 포함) null. */
  static BigDecimal locationQuotient(Measures m) {
    if (m.sameIndustry300m() == null
        || m.stores300m() == 0
        || m.nationalShare() == null
        || m.nationalShare().signum() == 0) {
      return null;
    }
    BigDecimal local =
        BigDecimal.valueOf(m.sameIndustry300m())
            .divide(BigDecimal.valueOf(m.stores300m()), MathContext.DECIMAL64);
    return local.divide(m.nationalShare(), MathContext.DECIMAL64);
  }

  private int rule(String metric, BigDecimal value) {
    Piecewise p =
        rules
            .rule(lifeScores.scoreVersion(), metric)
            .orElseThrow(() -> new IllegalStateException("상권 점수 규칙이 없어요: " + metric));
    return p.apply(value).setScale(0, RoundingMode.HALF_UP).intValueExact();
  }
}
