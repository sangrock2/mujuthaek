package kr.mujuthaek.api.user.repository;

import java.sql.Array;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.common.region.CityDistricts;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/**
 * 관심 조건 세 가지 (account.housing_interests·business_interests·support_interests)와 새 공고·정책 알림 대상자 찾기.
 *
 * <p>지역 맞추기: 회원 코드 u와 공고·정책 코드 n이 같은 시도(앞 2자리)이고, 같은 시군구이거나 둘 중 하나가 시도 전체(xx000)면 맞아요. 서울
 * 전체(11000)를 고른 회원은 마포구(11440) 공고를, 마포구를 고른 회원은 서울 전체 대상 정책을 받아요. 일반구가 있는 시(CityDistricts)와 그 구도
 * 맞아요: 수원시(41110)를 고른 회원은 장안구(41111) 공고를, 장안구를 고른 회원은 수원시 전체 공고를 받아요(2026-11-10 재검토: 수원시를 고른 회원에게 구
 * 공고 알림이 빠졌음).
 */
@Repository
public class InterestRepository {

  /** 지역이 맞는지 (회원 region_codes × :codes) */
  private static final String REGION_MATCH =
      """
      exists (select 1 from unnest(i.region_codes) u, unnest(cast(:codes as text[])) n
               where left(u, 2) = left(n, 2) and (u = n or u like '__000' or n like '__000'
                 or %s or %s))
      """
          .formatted(CityDistricts.sqlInCity("u", "n"), CityDistricts.sqlInCity("n", "u"));

  private final JdbcClient jdbc;

  public InterestRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  public record Housing(
      List<String> regionCodes, boolean includeNationwide, List<String> noticeTypes) {}

  public record Business(
      List<String> regionCodes,
      boolean includeNationwide,
      List<String> industryCodes,
      List<String> startupStages) {}

  public record Support(
      List<String> regionCodes, boolean includeNationwide, List<String> supportKinds) {}

  public Optional<Housing> housing(UUID userId) {
    return jdbc.sql(
            "select region_codes, include_nationwide, notice_types from account.housing_interests where user_id = :u")
        .param("u", userId)
        .query(
            (rs, i) ->
                new Housing(list(rs, "region_codes"), rs.getBoolean(2), list(rs, "notice_types")))
        .optional();
  }

  public Optional<Business> business(UUID userId) {
    return jdbc.sql(
            """
            select region_codes, include_nationwide, industry_codes, startup_stages
              from account.business_interests where user_id = :u
            """)
        .param("u", userId)
        .query(
            (rs, i) ->
                new Business(
                    list(rs, "region_codes"),
                    rs.getBoolean(2),
                    list(rs, "industry_codes"),
                    list(rs, "startup_stages")))
        .optional();
  }

  public Optional<Support> support(UUID userId) {
    return jdbc.sql(
            "select region_codes, include_nationwide, support_kinds from account.support_interests where user_id = :u")
        .param("u", userId)
        .query(
            (rs, i) ->
                new Support(list(rs, "region_codes"), rs.getBoolean(2), list(rs, "support_kinds")))
        .optional();
  }

  public void saveHousing(UUID userId, Housing h, Instant now) {
    jdbc.sql(
            """
            insert into account.housing_interests (user_id, region_codes, include_nationwide, notice_types, updated_at)
            values (:u, :regions, :nationwide, :types, :now)
            on conflict (user_id) do update set region_codes = excluded.region_codes,
                include_nationwide = excluded.include_nationwide, notice_types = excluded.notice_types,
                updated_at = excluded.updated_at
            """)
        .param("u", userId)
        .param("regions", h.regionCodes().toArray(String[]::new))
        .param("nationwide", h.includeNationwide())
        .param("types", h.noticeTypes().toArray(String[]::new))
        .param("now", now.atOffset(ZoneOffset.UTC))
        .update();
  }

  public void saveBusiness(UUID userId, Business b, Instant now) {
    jdbc.sql(
            """
            insert into account.business_interests
                (user_id, region_codes, include_nationwide, industry_codes, startup_stages, updated_at)
            values (:u, :regions, :nationwide, :industries, :stages, :now)
            on conflict (user_id) do update set region_codes = excluded.region_codes,
                include_nationwide = excluded.include_nationwide, industry_codes = excluded.industry_codes,
                startup_stages = excluded.startup_stages, updated_at = excluded.updated_at
            """)
        .param("u", userId)
        .param("regions", b.regionCodes().toArray(String[]::new))
        .param("nationwide", b.includeNationwide())
        .param("industries", b.industryCodes().toArray(String[]::new))
        .param("stages", b.startupStages().toArray(String[]::new))
        .param("now", now.atOffset(ZoneOffset.UTC))
        .update();
  }

  public void saveSupport(UUID userId, Support s, Instant now) {
    jdbc.sql(
            """
            insert into account.support_interests (user_id, region_codes, include_nationwide, support_kinds, updated_at)
            values (:u, :regions, :nationwide, :kinds, :now)
            on conflict (user_id) do update set region_codes = excluded.region_codes,
                include_nationwide = excluded.include_nationwide, support_kinds = excluded.support_kinds,
                updated_at = excluded.updated_at
            """)
        .param("u", userId)
        .param("regions", s.regionCodes().toArray(String[]::new))
        .param("nationwide", s.includeNationwide())
        .param("kinds", s.supportKinds().toArray(String[]::new))
        .param("now", now.atOffset(ZoneOffset.UTC))
        .update();
  }

  /**
   * {@code table}은 housing_interests·business_interests·support_interests 중 하나 (밖에서 받은 값을 넣지 않아요)
   */
  public int delete(String table, UUID userId) {
    return jdbc.sql("delete from account." + checked(table) + " where user_id = :u")
        .param("u", userId)
        .update();
  }

  /**
   * 새 공고·정책 알림을 받을 회원. 지역이 맞거나, 전국 대상이고 전국도 받기로 한 회원이에요.
   *
   * @param table 대상 관심 조건 테이블
   * @param codes 공고·정책 지역 (시군구 5자리 또는 시도 전체 xx000)
   * @param noticeType 주거 공고 유형 (housing_interests만, 모르면 null → 유형으로 거르지 않아요)
   */
  public List<UUID> audience(
      String table, List<String> codes, boolean nationwide, String noticeType) {
    String typeFilter =
        "housing_interests".equals(table)
            ? " and (cardinality(i.notice_types) = 0 or cast(:noticeType as text) is null or :noticeType = any(i.notice_types))"
            : "";
    var spec =
        jdbc.sql(
                "select i.user_id from account."
                    + checked(table)
                    + " i where ((:nationwide and i.include_nationwide) or "
                    + REGION_MATCH
                    + ")"
                    + typeFilter
                    + " order by i.user_id")
            .param("codes", codes.toArray(String[]::new))
            .param("nationwide", nationwide);
    if (!typeFilter.isEmpty()) {
      spec = spec.param("noticeType", noticeType, java.sql.Types.VARCHAR);
    }
    return spec.query(UUID.class).list();
  }

  private static String checked(String table) {
    return switch (table) {
      case "housing_interests", "business_interests", "support_interests" -> table;
      default -> throw new IllegalArgumentException("관심 조건 테이블이 아니에요: " + table);
    };
  }

  private static List<String> list(ResultSet rs, String column) throws SQLException {
    Array array = rs.getArray(column);
    return array == null ? List.of() : Arrays.asList((String[]) array.getArray());
  }
}
