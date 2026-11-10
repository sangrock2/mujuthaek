package kr.mujuthaek.api.area.repository;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import kr.mujuthaek.api.area.AreaTestDatabase;
import kr.mujuthaek.api.area.domain.Piecewise;
import org.junit.jupiter.api.Test;

class PostgresScoreRulesTest {

  private final PostgresScoreRules rules = new PostgresScoreRules(AreaTestDatabase.dataSource());

  @Test
  void workDistanceRuleMatchesThePlan() {
    // 3km 100 → 7km 80 → 15km 60 → 25km 30 → 40km 0, 그 사이는 직선
    Piecewise work = rules.rule("2026.1", "work_distance_m").orElseThrow();

    assertThat(work.apply(BigDecimal.valueOf(1000))).isEqualByComparingTo("100");
    assertThat(work.apply(BigDecimal.valueOf(3000))).isEqualByComparingTo("100");
    assertThat(work.apply(BigDecimal.valueOf(5000))).isEqualByComparingTo("90");
    assertThat(work.apply(BigDecimal.valueOf(7000))).isEqualByComparingTo("80");
    assertThat(work.apply(BigDecimal.valueOf(25000))).isEqualByComparingTo("30");
    assertThat(work.apply(BigDecimal.valueOf(40000))).isEqualByComparingTo("0");
    assertThat(work.apply(BigDecimal.valueOf(90000))).isEqualByComparingTo("0");
  }

  @Test
  void unknownVersionOrMetricIsEmpty() {
    assertThat(rules.rule("1999.1", "work_distance_m")).isEmpty();
    assertThat(rules.rule("2026.1", "no_such_metric")).isEmpty();
  }
}
