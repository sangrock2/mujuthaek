package kr.mujuthaek.api.eligibility.repository;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.LocalDate;
import kr.mujuthaek.api.TestDatabase;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

class CriteriaStoreTest {

  private final JdbcTemplate jdbc = new JdbcTemplate(TestDatabase.dataSource());
  private final CriteriaStore store = new CriteriaStore(jdbc);

  @BeforeEach
  void clean() {
    jdbc.update("delete from eligibility.criteria_sets");
  }

  @Test
  void findsByKindAndYearAndTheLatestYearInUse() {
    insert("MEDIAN_INCOME", 2025, "2025-01-01");
    insert("MEDIAN_INCOME", 2026, "2026-01-01");
    insert("MEDIAN_INCOME", 2027, "2027-01-01"); // 미리 넣어 둔 내년 값

    assertThat(store.find("MEDIAN_INCOME", 2026))
        .get()
        .satisfies(r -> assertThat(r.data()).contains("monthlyWon"));
    assertThat(store.find("RANK_CRITERIA", 2026)).isEmpty();
    assertThat(store.latestYear(LocalDate.of(2026, 10, 22))).contains(2026);
    assertThat(store.latestYear(LocalDate.of(2000, 1, 1))).isEmpty();
  }

  @Test
  void rejectsUnknownKinds() {
    assertThatThrownBy(() -> insert("LOTTO", 2026, "2026-01-01")).hasMessageContaining("check");
  }

  private void insert(String kind, int year, String validFrom) {
    jdbc.update(
        "insert into eligibility.criteria_sets (kind, year, valid_from, data) values (?, ?, ?::date, ?::jsonb)",
        kind,
        year,
        validFrom,
        "{\"monthlyWon\": {\"1\": 1000000}}");
  }
}
