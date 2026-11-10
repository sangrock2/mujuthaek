package kr.mujuthaek.api.area;

import static kr.mujuthaek.api.area.AreaTestDatabase.one;
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

/** 점수 규칙 2026.1과 직선 잇기 함수(area.piecewise). */
class AreaScoreRulesTest {

  @ParameterizedTest
  @CsvSource({
    "0, 100",
    "500, 100",
    "750, 85",
    "1000, 70",
    "1500, 55",
    "2000, 40",
    "2500, 20",
    "3000, 0",
    "9999, 0"
  })
  void stationDistanceRuleJoinsPointsWithStraightLines(int meters, int score) throws Exception {
    assertThat(
            one(
                "select area.piecewise("
                    + meters
                    + ", xs, ys)::int from area.score_rules"
                    + " where score_version = '2026.1' and metric = 'station_nearest_m'"))
        .isEqualTo(String.valueOf(score));
  }

  @Test
  void weightsOfEveryLifeCategorySumToOne() throws Exception {
    assertThat(
            one(
                "select string_agg(category || '=' || total, ',' order by category) from ("
                    + " select category, sum(weight) as total from area.score_weights"
                    + " where score_version = '2026.1' and score_kind = 'LIFE' group by category) s"))
        .isEqualTo("CONVENIENCE=1.0,HOSPITAL=1.0,PARK=1.0,SCHOOL=1.0,TRANSIT=1.0");
  }

  @Test
  void everyWeightedMetricHasARule() throws Exception {
    assertThat(
            one(
                "select count(*) from area.score_weights w left join area.score_rules r"
                    + " using (score_version, metric) where r.metric is null"))
        .isEqualTo("0");
  }
}
