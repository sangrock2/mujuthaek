package kr.mujuthaek.api.area.repository;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import javax.sql.DataSource;
import kr.mujuthaek.api.area.domain.AreaMetric;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/** 위치 상세(GET /areas/sites/{siteId})에 쓰는 저장된 세권 지표와 가장 가까운 역 이름, 점수 기준표. */
@Component
public final class PostgresSiteDetails {

  /** 위치의 지표 (근처에 그 시설이 없으면 빠져요)와 마지막 계산 시각. */
  public record Metrics(Map<AreaMetric, BigDecimal> values, Instant calculatedAt) {}

  /** 가장 가까운 도시철도역 이름·거리(m). */
  public record Station(String name, long meters) {}

  /** 점수 규칙 한 줄 (구간 xs → 점수 ys). */
  public record Rule(String metric, List<BigDecimal> xs, List<BigDecimal> ys) {}

  /** 생활권 항목 하나를 이루는 지표와 그 비중. */
  public record Weight(String category, String metric, BigDecimal weight) {}

  private final JdbcTemplate jdbc;

  public PostgresSiteDetails(DataSource dataSource) {
    this.jdbc = new JdbcTemplate(dataSource);
  }

  public Metrics metrics(UUID locationId) {
    Map<AreaMetric, BigDecimal> values = new EnumMap<>(AreaMetric.class);
    Instant[] latest = {null};
    jdbc.query(
        "select metric, value, calculated_at from area.location_metrics where location_id = ?",
        rs -> {
          values.put(AreaMetric.ofCode(rs.getString("metric")), rs.getBigDecimal("value"));
          Instant at = rs.getTimestamp("calculated_at").toInstant();
          if (latest[0] == null || at.isAfter(latest[0])) {
            latest[0] = at;
          }
        },
        locationId);
    return new Metrics(values, latest[0]);
  }

  /** KNN 후보 5개 중 타원체 거리가 가장 짧은 역 (세권 지표와 같은 방식). 역 자료가 없거나 좌표가 없으면 빈 값. */
  public Optional<Station> nearestStation(UUID locationId) {
    return jdbc
        .query(
            """
            select c.name, round(st_distance(c.geom, l.geom))::bigint as m
            from area.notice_locations l
            cross join lateral (select f.name, f.geom from area.facilities f where f.kind = 'SUBWAY_STATION'
                                order by f.geom <-> l.geom limit 5) c
            where l.location_id = ? and l.geom is not null
            order by st_distance(c.geom, l.geom) limit 1
            """,
            (rs, n) -> new Station(rs.getString("name"), rs.getLong("m")),
            locationId)
        .stream()
        .findFirst();
  }

  public List<Rule> rules(String scoreVersion) {
    return jdbc.query(
        "select metric, xs, ys from area.score_rules where score_version = ? order by metric",
        (rs, n) ->
            new Rule(
                rs.getString("metric"), decimals(rs.getArray("xs")), decimals(rs.getArray("ys"))),
        scoreVersion);
  }

  public List<Weight> lifeWeights(String scoreVersion) {
    return jdbc.query(
        "select category, metric, weight from area.score_weights"
            + " where score_version = ? and score_kind = 'LIFE' order by category, metric",
        (rs, n) ->
            new Weight(
                rs.getString("category"), rs.getString("metric"), rs.getBigDecimal("weight")),
        scoreVersion);
  }

  private static List<BigDecimal> decimals(java.sql.Array array) throws java.sql.SQLException {
    return java.util.Arrays.stream((Object[]) array.getArray()).map(v -> (BigDecimal) v).toList();
  }

  /** 여러 위치의 지표 (태그 계산용). 지표가 없는 위치는 빠져요. */
  public Map<UUID, Map<AreaMetric, BigDecimal>> metricsOf(java.util.Collection<UUID> locationIds) {
    Map<UUID, Map<AreaMetric, BigDecimal>> out = new java.util.HashMap<>();
    if (locationIds.isEmpty()) {
      return out;
    }
    jdbc.query(
        "select location_id, metric, value from area.location_metrics where location_id = any(?::uuid[])",
        rs -> {
          out.computeIfAbsent(
                  rs.getObject("location_id", UUID.class), k -> new EnumMap<>(AreaMetric.class))
              .put(AreaMetric.ofCode(rs.getString("metric")), rs.getBigDecimal("value"));
        },
        (Object) locationIds.toArray(UUID[]::new));
    return out;
  }
}
