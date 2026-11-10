package kr.mujuthaek.api.common.region;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

/** 지역 코드 조회. 다른 모듈도 지역 이름(regionName)을 붙일 때 써요. */
@Service
public class RegionQueryService {

  private final JdbcTemplate jdbc;

  public RegionQueryService(JdbcTemplate jdbc) {
    this.jdbc = jdbc;
  }

  public record Sigungu(String code, String name) {}

  public record Sido(String code, String name, String shortName, List<Sigungu> sigungus) {}

  public record RegionTree(LocalDate baseDate, List<Sido> sidos) {}

  /**
   * @param valid 폐지된 코드면 false, replacedBy가 바뀐 코드
   */
  public record Region(
      String code,
      String level,
      String name,
      String fullName,
      boolean valid,
      String replacedBy,
      LocalDate validTo) {}

  /** 유효한 시도와 그 아래 시군구 (코드 순). */
  public RegionTree tree() {
    Map<String, Sido> sidos = new LinkedHashMap<>();
    jdbc.query(
        "select code, name, short_name from common.regions where level = 'SIDO' and valid order by code",
        rs -> {
          sidos.put(
              rs.getString(1),
              new Sido(rs.getString(1), rs.getString(2), rs.getString(3), new ArrayList<>()));
        });
    jdbc.query(
        "select code, name, parent_code from common.regions where level = 'SIGUNGU' and valid order by code",
        rs -> {
          Sido sido = sidos.get(rs.getString(3));
          if (sido != null) {
            sido.sigungus().add(new Sigungu(rs.getString(1), rs.getString(2)));
          }
        });
    LocalDate baseDate =
        jdbc.queryForObject("select max(base_date) from common.regions", LocalDate.class);
    return new RegionTree(baseDate, List.copyOf(sidos.values()));
  }

  public Optional<Region> find(String code) {
    return jdbc
        .query(
            "select code, level, name, full_name, valid, replaced_by, valid_to from common.regions where code = ?",
            (rs, i) ->
                new Region(
                    rs.getString(1),
                    rs.getString(2),
                    rs.getString(3),
                    rs.getString(4),
                    rs.getBoolean(5),
                    rs.getString(6),
                    rs.getObject(7, LocalDate.class)),
            code)
        .stream()
        .findFirst();
  }

  /** 여러 코드의 화면 이름을 한 번에 (목록용). 모르는 코드는 빠져요. */
  public Map<String, String> displayNames(java.util.Collection<String> codes) {
    List<String> distinct = codes.stream().filter(c -> c != null).distinct().toList();
    Map<String, String> out = new java.util.HashMap<>();
    if (distinct.isEmpty()) {
      return out;
    }
    new org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate(jdbc)
        .query(
            """
            select r.code, coalesce(s.short_name || ' ' || r.name, r.short_name, r.name)
            from common.regions r left join common.regions s on s.code = r.parent_code
            where r.code in (:codes)
            """,
            java.util.Map.of("codes", distinct),
            rs -> {
              out.put(rs.getString(1), rs.getString(2));
            });
    return out;
  }

  /** 화면에 붙일 지역 이름 ("서울 마포구"). 모르는 코드면 null. */
  public String displayName(String code) {
    if (code == null) {
      return null;
    }
    return jdbc
        .query(
            """
            select coalesce(s.short_name || ' ' || r.name, r.short_name, r.name)
            from common.regions r left join common.regions s on s.code = r.parent_code
            where r.code = ?
            """,
            (rs, i) -> rs.getString(1),
            code)
        .stream()
        .findFirst()
        .orElse(null);
  }

  /**
   * 이름으로 찾은 지역. 하나로 정해지면 code, 같은 이름이 여러 곳이면 code는 null이고 candidates에 후보.
   *
   * @param code 지금 유효한 코드 (시도 2자리 또는 시군구 5자리)
   * @param candidates 하나로 못 정했을 때의 후보 코드 (못 찾으면 빈 목록)
   */
  public record RegionMatch(String code, List<String> candidates) {

    static RegionMatch of(List<String> codes) {
      return codes.size() == 1
          ? new RegionMatch(codes.get(0), List.of())
          : new RegionMatch(null, List.copyOf(codes));
    }
  }

  /**
   * 주소 글자의 시도·시군구 이름으로 지금 코드를 찾아요. 폐지된 이름(강원도, 광주광역시 동구)은 바뀐 코드로 가요.
   *
   * <ul>
   *   <li>시도: 정식 이름(서울특별시), 짧은 이름(서울), 짧은 이름 + 시·도(서울시, 경기도)
   *   <li>시군구: 이름(마포구), 일반구는 시와 같이(수원시 장안구) 또는 구만(장안구), 시만(수원시)
   *   <li>시도 없이 시군구만 오면 전국에서 찾고, 같은 이름(중구·동구·서구…)이 여러 곳이면 후보로 돌려줘요
   * </ul>
   *
   * @param sidoName 시도 이름 (없으면 null)
   * @param sigunguName 시군구 이름 (없으면 null → 시도 코드)
   */
  public RegionMatch resolve(String sidoName, String sigunguName) {
    List<String> sidos =
        sidoName == null || sidoName.isBlank() ? List.of() : sidoCodes(sidoName.strip());
    if (sigunguName == null || sigunguName.isBlank()) {
      return RegionMatch.of(sidos);
    }
    if (sidoName != null && !sidoName.isBlank() && sidos.isEmpty()) {
      return RegionMatch.of(List.of());
    }
    String name = sigunguName.strip().replaceAll("\\s+", " ");
    List<String> found =
        jdbc.queryForList(
            """
            select distinct x.code
            from common.regions r
            -- 지금 코드, 폐지됐으면 바뀐 코드, 갈라진 것(인천 중구 → 제물포구·영종구)은 대응표의 새 시군구들
            cross join lateral (
              select case when r.valid then r.code else r.replaced_by end as code
              union all
              select left(c.new_code, 5) from common.region_code_changes c
              where not r.valid and r.replaced_by is null and c.old_code = r.code || '00000'
            ) x
            where r.level = 'SIGUNGU' and x.code is not null
              and (r.name = ? or r.name like '% ' || ?)
              and (cardinality(?::text[]) = 0
                   or r.parent_code = any(?::text[])
                   or exists (select 1 from common.regions p
                              where p.code = r.parent_code and p.replaced_by = any(?::text[])))
            order by 1
            """,
            String.class,
            name,
            name,
            sidos.toArray(String[]::new),
            sidos.toArray(String[]::new),
            sidos.toArray(String[]::new));
    return RegionMatch.of(found);
  }

  private List<String> sidoCodes(String name) {
    return jdbc
        .queryForList(
            """
        select distinct coalesce(case when valid then code end, replaced_by)
        from common.regions
        where level = 'SIDO'
          and (name = ? or short_name = ? or short_name || '시' = ? or short_name || '도' = ?)
        order by 1
        """,
            String.class,
            name,
            name,
            name,
            name)
        .stream()
        .filter(c -> c != null)
        .toList();
  }

  /** 법정동코드(10자리)를 지금 코드로. 2026 개편으로 폐지된 코드는 대응표의 지금 코드(여러 개일 수 있음), 대응이 없으면 받은 코드 그대로. */
  public List<String> toCurrent(String legalDongCode) {
    if (legalDongCode == null || !legalDongCode.matches("[0-9]{10}")) {
      return List.of();
    }
    List<String> changed =
        jdbc.queryForList(
            "select new_code from common.region_code_changes where old_code = ? order by new_code",
            String.class,
            legalDongCode);
    return changed.isEmpty() ? List.of(legalDongCode) : changed;
  }

  /** ETag용: 코드표가 바뀌면 달라지는 값. */
  String version() {
    return jdbc.queryForObject(
        "select count(*) || '-' || coalesce(extract(epoch from max(updated_at))::bigint, 0) from common.regions",
        String.class);
  }
}
