package kr.mujuthaek.api.area.repository;

import java.math.BigDecimal;
import java.util.Optional;
import java.util.UUID;
import javax.sql.DataSource;
import kr.mujuthaek.api.area.domain.CommercialIndustry;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/**
 * 상권 점수에 쓰는 값을 요청 때 재요 (7단계, 위치 하나에 수십 ms): 300m 안 점포 수·같은 업종 수, 그 업종의 전국 비율, 가장 가까운 도시철도역. 가장 가까운
 * 역은 세권 지표처럼 KNN 후보 5개 중 타원체 거리가 가장 짧은 곳이에요.
 */
@Component
public final class PostgresCommercialMeasures {

  /**
   * @param sameIndustry300m 업종이 없으면 null
   * @param nationalShare 그 업종의 전국 비율 (업종이 없거나 아직 비율이 없으면 null)
   * @param stationName 역 자료가 없으면 null
   */
  public record Measures(
      long stores300m,
      Long sameIndustry300m,
      BigDecimal nationalShare,
      String stationName,
      Long stationMeters) {}

  private static final String SQL =
      """
      select (select count(*) from area.stores s where st_dwithin(s.geom, l.geom, 300)) as stores,
             case when ?::text is null then null
                  else (select count(*) from area.stores s
                        where st_dwithin(s.geom, l.geom, 300)
                          and case when ?::text = 'RETAIL' then s.large_code = 'G2' else s.industry_group = ?::text end)
             end as same,
             (select store_count::numeric / nullif(total_count, 0) from area.industry_shares where industry = ?::text) as share,
             st.name as station, st.m as station_m
      from area.notice_locations l
      left join lateral (
        select c.name, round(st_distance(c.geom, l.geom))::bigint as m
        from (select f.name, f.geom from area.facilities f where f.kind = 'SUBWAY_STATION'
              order by f.geom <-> l.geom limit 5) c
        order by st_distance(c.geom, l.geom) limit 1
      ) st on true
      where l.location_id = ? and l.geom is not null
      """;

  private final JdbcTemplate jdbc;

  public PostgresCommercialMeasures(DataSource dataSource) {
    this.jdbc = new JdbcTemplate(dataSource);
  }

  /** 좌표가 있는 위치면 값을, 없는 위치·좌표 없는 위치면 빈 값. */
  public Optional<Measures> measure(UUID locationId, CommercialIndustry industry) {
    String code = industry == null ? null : industry.name();
    return jdbc
        .query(
            SQL,
            (rs, n) ->
                new Measures(
                    rs.getLong("stores"),
                    rs.getObject("same") == null ? null : rs.getLong("same"),
                    rs.getBigDecimal("share"),
                    rs.getString("station"),
                    rs.getObject("station_m") == null ? null : rs.getLong("station_m")),
            code,
            code,
            code,
            code,
            locationId)
        .stream()
        .findFirst();
  }
}
