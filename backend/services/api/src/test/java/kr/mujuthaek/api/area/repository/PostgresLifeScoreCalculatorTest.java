package kr.mujuthaek.api.area.repository;

import static kr.mujuthaek.api.area.AreaTestDatabase.exec;
import static kr.mujuthaek.api.area.AreaTestDatabase.one;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.area.AreaTestDatabase;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * 생활권 항목 점수. 지표를 직접 넣고 손으로 계산한 점수와 비교해요.
 *
 * <pre>
 * TRANSIT     역 750m → 85 × 0.7 + 버스 3곳 → 60 × 0.3            = 77.5 → 78
 * SCHOOL      초등 없음 → 0 × 0.6 + 중 1 → 50 × 0.2 + 고 2 → 100 × 0.2 = 30
 * PARK        공원 400m → 90 × 0.7 + 면적 45,000㎡ → 45 × 0.3       = 76.5 → 77 (HALF_EVEN이면 76)
 * CONVENIENCE 편의점 5 → 100 × 0.6 + 슈퍼 없음 → 0 × 0.4          = 60
 * HOSPITAL    지표 없음                                         = 0
 * </pre>
 */
class PostgresLifeScoreCalculatorTest {

  private static final PostgresLifeScoreCalculator calculator =
      new PostgresLifeScoreCalculator(AreaTestDatabase.dataSource());

  private final UUID at = UUID.randomUUID();

  @BeforeEach
  void insertLocationWithMetrics() throws Exception {
    exec(
        "insert into area.notice_locations (location_id, notice_id, notice_location_id, notice_version, kind,"
            + " address_text, geom, status, method) values ('"
            + at
            + "', gen_random_uuid(), 'building-a', 1, 'COMPLEX', '시험 위치 점수',"
            + " st_makepoint(125.8, 34.8)::geography, 'OK', 'FILE')");
    exec(
        "insert into area.location_metrics (location_id, metric, value) select '"
            + at
            + "', metric, value from (values ('station_nearest_m', 750), ('bus_stop_count_300m', 3),"
            + " ('middle_count_1km', 1), ('high_count_1km', 2), ('park_nearest_m', 400),"
            + " ('park_area_1km_m2', 45000), ('convenience_store_count_300m', 5),"
            + " ('store_count_300m', 40)) v(metric, value)");
  }

  @AfterEach
  void deleteLocation() throws Exception {
    exec("delete from area.notice_locations where address_text like '시험 위치 점수%'");
  }

  @Test
  void scoresMatchHandCalculation() throws Exception {
    assertThat(calculator.calculate(List.of(at), "2026.1")).isEqualTo(5);

    assertThat(scores(at))
        .isEqualTo("CONVENIENCE=60,HOSPITAL=0,PARK=77,SCHOOL=30,TRANSIT=78 (2026.1)");
  }

  @Test
  void sameInputTwiceGivesSameScores() throws Exception {
    calculator.calculate(List.of(at), "2026.1");
    String first = scores(at);
    calculator.calculate(List.of(at), "2026.1");

    assertThat(scores(at)).isEqualTo(first);
    assertThat(one("select count(*) from area.location_scores where location_id = '" + at + "'"))
        .isEqualTo("5");
  }

  @Test
  void sqlRoundingHalfUpMatchesJava() throws Exception {
    // SQL round(numeric)은 0.5를 0에서 먼 쪽으로 — 자바 TotalScore의 HALF_UP과 같아요
    assertThat(one("select round(76.5::numeric) || ',' || round(77.5::numeric)"))
        .isEqualTo("77,78");
  }

  @Test
  void unknownVersionFailsAndKeepsScores() throws Exception {
    calculator.calculate(List.of(at), "2026.1");

    assertThatThrownBy(() -> calculator.calculate(List.of(at), "1999.9"))
        .isInstanceOf(IllegalArgumentException.class);
    assertThat(scores(at)).startsWith("CONVENIENCE=60");
  }

  @Test
  void failedLocationGetsNoScores() throws Exception {
    UUID failed = UUID.randomUUID();
    exec(
        "insert into area.notice_locations (location_id, notice_id, notice_location_id, notice_version, kind,"
            + " address_text, status, fail_reason) values ('"
            + failed
            + "', gen_random_uuid(), 'building-a', 1, 'COMPLEX', '시험 위치 점수 실패', 'FAILED', 'NOT_FOUND')");

    assertThat(calculator.calculate(List.of(failed), "2026.1")).isZero();
  }

  private static String scores(UUID location) throws Exception {
    return one(
        "select string_agg(category || '=' || score, ',' order by category)"
            + " || ' (' || min(score_version) || ')' from area.location_scores"
            + " where score_kind = 'LIFE' and location_id = '"
            + location
            + "'");
  }
}
