package kr.mujuthaek.api.area.domain;

import static kr.mujuthaek.api.area.domain.LifeCategory.CONVENIENCE;
import static kr.mujuthaek.api.area.domain.LifeCategory.HOSPITAL;
import static kr.mujuthaek.api.area.domain.LifeCategory.PARK;
import static kr.mujuthaek.api.area.domain.LifeCategory.SCHOOL;
import static kr.mujuthaek.api.area.domain.LifeCategory.TRANSIT;
import static kr.mujuthaek.api.area.domain.LifeCategory.WORK;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class TotalScoreTest {

  private static final Piecewise STATION =
      Piecewise.of(new long[] {500, 1000, 2000, 3000}, new long[] {100, 70, 40, 0});
  private static final Piecewise WORK_DISTANCE =
      Piecewise.of(new long[] {3000, 7000, 15000, 25000, 40000}, new long[] {100, 80, 60, 30, 0});

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
  void piecewiseMatchesSqlRuleBoundaries(int meters, int score) {
    assertThat(STATION.apply(BigDecimal.valueOf(meters)))
        .isEqualByComparingTo(BigDecimal.valueOf(score));
  }

  @Test
  void workDistanceOf8point4KmIs76point5() {
    assertThat(WORK_DISTANCE.apply(new BigDecimal("8400"))).isEqualByComparingTo("76.5");
  }

  @Test
  void halfRoundsUpLikeSql() {
    // 77·76 같은 비중 → 76.5 → 77 (HALF_EVEN이면 76)
    assertThat(TotalScore.of(Map.of(PARK, d("77"), SCHOOL, d("76")), Map.of(PARK, 1, SCHOOL, 1)))
        .isEqualTo(77);
    // 직장 76.5 하나만 → 77
    assertThat(TotalScore.of(Map.of(WORK, d("76.5")), Map.of(WORK, 3))).isEqualTo(77);
    // 74.5 → 75 (HALF_EVEN이면 74)
    assertThat(TotalScore.of(Map.of(PARK, d("74.5")), Map.of())).isEqualTo(75);
  }

  @Test
  void weightedAverageOverCategoriesWithScores() {
    Map<LifeCategory, BigDecimal> scores =
        Map.of(
            CONVENIENCE,
            d("52"),
            HOSPITAL,
            d("55"),
            PARK,
            d("100"),
            SCHOOL,
            d("73"),
            TRANSIT,
            d("36"),
            WORK,
            d("76.5"));
    Map<LifeCategory, Integer> weights =
        Map.of(CONVENIENCE, 8, HOSPITAL, 6, PARK, 2, SCHOOL, 4, TRANSIT, 5, WORK, 3);
    // (416 + 330 + 200 + 292 + 180 + 229.5) ÷ 28 = 58.83… → 59
    assertThat(TotalScore.of(scores, weights)).isEqualTo(59);
  }

  @Test
  void workIsLeftOutWhenNotGiven() {
    // 직장 가중치가 커도 직장 점수가 없으면 나머지만으로
    assertThat(
            TotalScore.of(
                Map.of(PARK, d("80"), TRANSIT, d("40")), Map.of(PARK, 1, TRANSIT, 1, WORK, 10)))
        .isEqualTo(60);
  }

  @Test
  void allZeroWeightsMeanEqualWeights() {
    assertThat(TotalScore.of(Map.of(PARK, d("80"), TRANSIT, d("41")), Map.of(PARK, 0)))
        .isEqualTo(61);
  }

  @Test
  void sameInputSameScore() {
    Map<LifeCategory, BigDecimal> scores =
        Map.of(PARK, d("33"), HOSPITAL, d("67"), SCHOOL, d("90"));
    Map<LifeCategory, Integer> weights = Map.of(PARK, 7, HOSPITAL, 2, SCHOOL, 9);
    assertThat(TotalScore.of(scores, weights))
        .isEqualTo(TotalScore.of(Map.copyOf(scores), Map.copyOf(weights)));
  }

  @Test
  void rejectsBadInput() {
    assertThatThrownBy(() -> TotalScore.of(Map.of(), Map.of()))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> TotalScore.of(Map.of(PARK, d("1")), Map.of(PARK, -1)))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> Piecewise.of(new long[] {2, 1}, new long[] {0, 1}))
        .isInstanceOf(IllegalArgumentException.class);
  }

  private static BigDecimal d(String v) {
    return new BigDecimal(v);
  }
}
