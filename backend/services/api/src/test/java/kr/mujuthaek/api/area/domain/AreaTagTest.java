package kr.mujuthaek.api.area.domain;

import static kr.mujuthaek.api.area.domain.AreaMetric.CLINIC_COUNT_500M;
import static kr.mujuthaek.api.area.domain.AreaMetric.CONVENIENCE_STORE_COUNT_300M;
import static kr.mujuthaek.api.area.domain.AreaMetric.ELEMENTARY_NEAREST_M;
import static kr.mujuthaek.api.area.domain.AreaMetric.HIGH_COUNT_1KM;
import static kr.mujuthaek.api.area.domain.AreaMetric.MIDDLE_COUNT_1KM;
import static kr.mujuthaek.api.area.domain.AreaMetric.PARK_NEAREST_M;
import static kr.mujuthaek.api.area.domain.AreaMetric.STATION_NEAREST_M;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class AreaTagTest {

  @Test
  void boundaryValuesAreIncluded() {
    assertThat(
            AreaTag.of(
                Map.of(
                    STATION_NEAREST_M, d("500"),
                    ELEMENTARY_NEAREST_M, d("300"),
                    MIDDLE_COUNT_1KM, d("1"),
                    HIGH_COUNT_1KM, d("1"),
                    PARK_NEAREST_M, d("500"),
                    CONVENIENCE_STORE_COUNT_300M, d("3"),
                    CLINIC_COUNT_500M, d("3"))))
        .containsExactlyInAnyOrder(AreaTag.values());
  }

  @Test
  void justOutsideBoundariesGetsNoTag() {
    assertThat(
            AreaTag.of(
                Map.of(
                    STATION_NEAREST_M, d("500.01"),
                    ELEMENTARY_NEAREST_M, d("1000.01"),
                    MIDDLE_COUNT_1KM, d("2"),
                    PARK_NEAREST_M, d("500.01"),
                    CONVENIENCE_STORE_COUNT_300M, d("2"),
                    CLINIC_COUNT_500M, d("2"))))
        .isEmpty();
  }

  @Test
  void schoolNeedsTwoMiddleOrHighSchools() {
    assertThat(AreaTag.of(Map.of(ELEMENTARY_NEAREST_M, d("900"), HIGH_COUNT_1KM, d("1"))))
        .isEmpty();
    assertThat(AreaTag.of(Map.of(ELEMENTARY_NEAREST_M, d("900"), HIGH_COUNT_1KM, d("2"))))
        .containsExactly(AreaTag.SCHOOL);
  }

  @Test
  void missingMetricsMeanNoTag() {
    assertThat(AreaTag.of(Map.of())).isEmpty();
  }

  @ParameterizedTest
  @CsvSource({"0, 0", "1, 1", "670, 13", "670.01, 14", "420, 9", "1000, 20"})
  void walkMinutesRoundUpStraightDistanceTimesDetour(String meters, int minutes) {
    assertThat(WalkMinutes.of(d(meters))).isEqualTo(minutes);
  }

  @Test
  void walkMinutesRejectNegativeDistance() {
    assertThatThrownBy(() -> WalkMinutes.of(d("-1"))).isInstanceOf(IllegalArgumentException.class);
  }

  private static BigDecimal d(String v) {
    return new BigDecimal(v);
  }
}
