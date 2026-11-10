package kr.mujuthaek.api.eligibility.repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/**
 * 관리자 기준값 화면의 쓰기·기록 (eligibility.criteria_sets, criteria_set_history, regulated_areas). 판정이 읽는 쪽은
 * {@link CriteriaStore} 그대로예요.
 */
@Repository
public class CriteriaAdminStore {

  private final JdbcClient jdbc;

  public CriteriaAdminStore(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  /** 그 종류의 연도별 값 (최근 연도부터). */
  public List<CriteriaSet> sets(String kind) {
    return jdbc.sql(
            "select kind, year, valid_from, data::text as data, source, updated_by, updated_at"
                + " from eligibility.criteria_sets where kind = :kind order by year desc")
        .param("kind", kind)
        .query(CriteriaAdminStore::set)
        .list();
  }

  public Optional<CriteriaSet> find(String kind, int year) {
    return jdbc.sql(
            "select kind, year, valid_from, data::text as data, source, updated_by, updated_at"
                + " from eligibility.criteria_sets where kind = :kind and year = :year")
        .param("kind", kind)
        .param("year", year)
        .query(CriteriaAdminStore::set)
        .optional();
  }

  /** 넣거나 바꿔요. 바꾸면 바꾸기 전 값을 기록에 남겨요. */
  public void save(
      String kind, int year, LocalDate validFrom, String data, String source, String admin) {
    jdbc.sql(
            "insert into eligibility.criteria_set_history (kind, year, valid_from, data, source,"
                + " updated_by, updated_at, replaced_by) select kind, year, valid_from, data,"
                + " source, updated_by, updated_at, :admin from eligibility.criteria_sets where"
                + " kind = :kind and year = :year")
        .param("kind", kind)
        .param("year", year)
        .param("admin", admin)
        .update();
    jdbc.sql(
            "insert into eligibility.criteria_sets (kind, year, valid_from, data, source,"
                + " updated_by, updated_at) values (:kind, :year, :validFrom, cast(:data as jsonb),"
                + " :source, :admin, now()) on conflict (kind, year) do update set valid_from ="
                + " excluded.valid_from, data = excluded.data, source = excluded.source, updated_by"
                + " = excluded.updated_by, updated_at = now()")
        .param("kind", kind)
        .param("year", year)
        .param("validFrom", validFrom)
        .param("data", data)
        .param("source", source)
        .param("admin", admin)
        .update();
  }

  /** 바꾼 기록 (최근 것부터). */
  public List<History> history(String kind, int limit) {
    return jdbc.sql(
            "select kind, year, valid_from, data::text as data, source, updated_by, updated_at,"
                + " replaced_at, replaced_by from eligibility.criteria_set_history where kind ="
                + " :kind order by replaced_at desc, id desc limit :limit")
        .param("kind", kind)
        .param("limit", limit)
        .query(
            (rs, i) ->
                new History(
                    set(rs, i),
                    rs.getObject("replaced_at", OffsetDateTime.class),
                    rs.getString("replaced_by")))
        .list();
  }

  /** 규제지역 (지정일 최근부터). activeOn이 있으면 그날 지정 중인 것만. */
  public List<RegulatedArea> regulatedAreas(LocalDate activeOn) {
    return jdbc.sql(
            "select id, region_code, kind, scope_note, valid_from, valid_until, source, updated_by,"
                + " updated_at from eligibility.regulated_areas where cast(:day as date) is null or"
                + " (valid_from <= :day and (valid_until is null or valid_until >= :day)) order by"
                + " valid_from desc, region_code")
        .param("day", activeOn)
        .query(CriteriaAdminStore::area)
        .list();
  }

  public void addRegulatedArea(RegulatedArea area) {
    jdbc.sql(
            "insert into eligibility.regulated_areas (id, region_code, kind, scope_note,"
                + " valid_from, valid_until, source, updated_by) values (:id, :region, :kind,"
                + " :scope, :from, :until, :source, :admin)")
        .param("id", area.id())
        .param("region", area.regionCode())
        .param("kind", area.kind())
        .param("scope", area.scopeNote())
        .param("from", area.validFrom())
        .param("until", area.validUntil())
        .param("source", area.source())
        .param("admin", area.updatedBy())
        .update();
  }

  /** 해제일을 넣어요. 바꾼 건수. */
  public int endRegulatedArea(UUID id, LocalDate until, String admin) {
    return jdbc.sql(
            "update eligibility.regulated_areas set valid_until = :until, updated_by = :admin,"
                + " updated_at = now() where id = :id and valid_from <= :until")
        .param("id", id)
        .param("until", until)
        .param("admin", admin)
        .update();
  }

  public Optional<RegulatedArea> findRegulatedArea(UUID id) {
    return jdbc.sql(
            "select id, region_code, kind, scope_note, valid_from, valid_until, source, updated_by,"
                + " updated_at from eligibility.regulated_areas where id = :id")
        .param("id", id)
        .query(CriteriaAdminStore::area)
        .optional();
  }

  private static CriteriaSet set(ResultSet rs, int i) throws SQLException {
    return new CriteriaSet(
        rs.getString("kind"),
        rs.getInt("year"),
        rs.getObject("valid_from", LocalDate.class),
        rs.getString("data"),
        rs.getString("source"),
        rs.getString("updated_by"),
        rs.getObject("updated_at", OffsetDateTime.class));
  }

  private static RegulatedArea area(ResultSet rs, int i) throws SQLException {
    return new RegulatedArea(
        rs.getObject("id", UUID.class),
        rs.getString("region_code"),
        rs.getString("kind"),
        rs.getString("scope_note"),
        rs.getObject("valid_from", LocalDate.class),
        rs.getObject("valid_until", LocalDate.class),
        rs.getString("source"),
        rs.getString("updated_by"),
        rs.getObject("updated_at", OffsetDateTime.class));
  }

  /** 기준값 한 해. data는 jsonb 글자 그대로. */
  public record CriteriaSet(
      String kind,
      int year,
      LocalDate validFrom,
      String data,
      String source,
      String updatedBy,
      OffsetDateTime updatedAt) {}

  /** 바뀌기 전 값과 바뀐 때·바꾼 사람. */
  public record History(CriteriaSet before, OffsetDateTime replacedAt, String replacedBy) {}

  /** 규제지역 한 줄. */
  public record RegulatedArea(
      UUID id,
      String regionCode,
      String kind,
      String scopeNote,
      LocalDate validFrom,
      LocalDate validUntil,
      String source,
      String updatedBy,
      OffsetDateTime updatedAt) {}
}
