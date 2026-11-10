package kr.mujuthaek.api.eligibility.repository;

import java.time.LocalDate;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

/** eligibility.criteria_sets 읽기. 값은 jsonb 그대로 돌려주고 해석은 서비스가 해요. */
@Repository
public class CriteriaStore {

  private final JdbcTemplate jdbc;

  public CriteriaStore(JdbcTemplate jdbc) {
    this.jdbc = jdbc;
  }

  public record CriteriaRow(String kind, int year, LocalDate validFrom, String data) {}

  public Optional<CriteriaRow> find(String kind, int year) {
    return jdbc
        .query(
            "select kind, year, valid_from, data::text from eligibility.criteria_sets where kind = ? and year = ?",
            (rs, i) ->
                new CriteriaRow(
                    rs.getString(1),
                    rs.getInt(2),
                    rs.getObject(3, LocalDate.class),
                    rs.getString(4)),
            kind,
            year)
        .stream()
        .findFirst();
  }

  /**
   * 고시된 소득 기준 월액 (eligibility.base_values, 가구원 수 → 원). criteria_sets에 그해 값이 없을 때 써요. 도시근로자 소득은
   * URBAN_WORKER_INCOME·URBAN_WORKER_AVERAGE_INCOME 두 이름이 있어서 kind를 여러 개 받아요.
   */
  public java.util.Map<String, Long> baseIncome(List<String> kinds, int year) {
    java.util.Map<String, Long> out = new java.util.LinkedHashMap<>();
    var named = new org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate(jdbc);
    named.query(
        """
        select household_size, amount_won from eligibility.base_values
        where kind in (:kinds) and year = :year and program = '' and household_size > 0
        order by household_size, kind
        """,
        java.util.Map.of("kinds", kinds, "year", year),
        rs -> {
          out.putIfAbsent(String.valueOf(rs.getInt(1)), rs.getLong(2));
        });
    return out;
  }

  /** 자산 기준 금액들 (주택 유형마다 다른 상한, 그해와 전해). 판정 입력의 자산 구간 경계로 써요. */
  public List<Long> assetCuts(String kind, int year) {
    return jdbc.queryForList(
        """
        select distinct amount_won from eligibility.base_values
        where kind = ? and year in (?, ?) order by amount_won
        """,
        Long.class,
        kind,
        year,
        year - 1);
  }

  /** 고시 값(base_values)이 있는 가장 최근 연도 (그해까지). criteria_sets가 비었을 때 써요. */
  public Optional<Integer> latestBaseYear(int maxYear) {
    List<Integer> years =
        jdbc.queryForList(
            "select max(year) from eligibility.base_values where year <= ? and kind = 'MEDIAN_INCOME'",
            Integer.class,
            maxYear);
    return years.isEmpty() ? Optional.empty() : Optional.ofNullable(years.get(0));
  }

  /** 그날 쓰는 값이 있는 가장 최근 연도 (valid_from이 그날 이전인 것 중). */
  public Optional<Integer> latestYear(LocalDate day) {
    List<Integer> years =
        jdbc.queryForList(
            "select max(year) from eligibility.criteria_sets where valid_from <= ?",
            Integer.class,
            java.sql.Date.valueOf(day));
    return years.isEmpty() ? Optional.empty() : Optional.ofNullable(years.get(0));
  }
}
