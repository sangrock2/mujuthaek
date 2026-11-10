package kr.mujuthaek.api.area;

import static kr.mujuthaek.api.area.AreaTestDatabase.exec;
import static kr.mujuthaek.api.area.AreaTestDatabase.one;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

/** area 기초 데이터 테이블이 Flyway로 만들어지고, 적재에 쓰는 SQL 함수가 동작하는지. */
class AreaMigrationTest {

  @Test
  void createsBaseDataTables() throws Exception {
    assertThat(
            one(
                "select string_agg(table_name, ',' order by table_name) from information_schema.tables"
                    + " where table_schema = 'area'"))
        .isEqualTo(
            "address_points,area_reports,facilities,industry_group_rules,industry_shares,load_runs,location_metrics,"
                + "location_scores,notice_locations,region_boundaries,road_names,score_rules,"
                + "score_weights,stores");
  }

  @Test
  void trigramOperatorsWorkFromAnAppConnection() throws Exception {
    // pg_trgm은 public에 있어야 앱 연결(기본 search_path)에서 %·similarity를 찾아요
    assertThat(
            one(
                "select extnamespace::regnamespace::text from pg_extension where extname = 'pg_trgm'"))
        .isEqualTo("public");
    assertThat(one("select round(similarity('초량상로', '초량상노')::numeric, 2)")).isEqualTo("0.43");
    assertThat(one("select '초량상로' % '초량상노'")).isEqualTo("t");
  }

  @Test
  void noticeLocationIdIsUniqueOnlyWithinANotice() throws Exception {
    // notice의 위치 ID(locations[].id)는 공고 안에서만 유일해요: 다른 공고는 같은 ID를 써도 되고, 같은 공고 안에서는 한 줄
    String a = java.util.UUID.randomUUID().toString();
    String b = java.util.UUID.randomUUID().toString();
    String insert =
        "insert into area.notice_locations (notice_id, notice_location_id, notice_version, kind,"
            + " address_text, status, fail_reason) values ('%s', 'building-a', 1, 'COMPLEX',"
            + " '시험 위치 유일', 'FAILED', 'NOT_FOUND')";
    try {
      exec(insert.formatted(a));
      exec(insert.formatted(b));
      assertThat(
              one(
                  "select count(distinct location_id) from area.notice_locations"
                      + " where notice_location_id = 'building-a' and address_text = '시험 위치 유일'"))
          .isEqualTo("2");
      assertThatThrownBy(() -> exec(insert.formatted(a)))
          .hasMessageContaining("notice_locations_notice_idx");
    } finally {
      exec("delete from area.notice_locations where address_text = '시험 위치 유일'");
    }
  }

  @Test
  void createsPartialSpatialIndexesForMetrics() throws Exception {
    assertThat(
            one(
                "select count(*) from pg_indexes where schemaname = 'area'"
                    + " and indexname in ('facilities_subway_gix', 'facilities_bus_gix',"
                    + " 'facilities_school_gix', 'facilities_park_gix', 'facilities_hosp2_gix',"
                    + " 'facilities_clinic_gix', 'stores_conv_gix', 'stores_mart_gix')"))
        .isEqualTo("8");
  }

  @Test
  void uuidV7FunctionMakesVersion7Ids() throws Exception {
    assertThat(one("select substring(area.uuid_v7()::text, 15, 1)")).isEqualTo("7");
  }

  @Test
  void geographyWorksWithFlywaySearchPath() throws Exception {
    // PostGIS 타입과 함수는 public 스키마에 있어요. 마이그레이션이 geography 칸을 만들었으면 찾은 거예요.
    assertThat(
            one(
                "select udt_name from information_schema.columns"
                    + " where table_schema = 'area' and table_name = 'facilities' and column_name = 'geom'"))
        .isEqualTo("geography");
  }

  @Test
  void dataDateColumnsExplainTheirMeaning() throws Exception {
    for (String table :
        new String[] {
          "area.stores", "area.facilities", "area.address_points", "area.region_boundaries"
        }) {
      assertThat(
              one(
                  "select col_description(attrelid, attnum) from pg_attribute"
                      + " where attrelid = '"
                      + table
                      + "'::regclass and attname = 'data_date'"))
          .contains("마지막으로 바뀐 적재", "area.load_runs.data_date");
    }
  }

  @Test
  void boundaryWktIsTransformedFromUtmkAndBadWktIsNull() throws Exception {
    // 청운동 경계 첫 점 근처(UTM-K) → 북위 37.59, 동경 126.98 부근
    assertThat(
            one(
                "select round(st_y(st_centroid(g))::numeric, 2) || ',' || round(st_x(st_centroid(g))::numeric, 2)"
                    + " || ',' || geometrytype(g) from (select area.boundary_from_utmk_wkt("
                    + "'POLYGON((953700 1954605, 953800 1954605, 953800 1954705, 953700 1954705, 953700 1954605))') g) s"))
        .isEqualTo("37.59,126.98,MULTIPOLYGON");
    assertThat(one("select area.boundary_from_utmk_wkt('POLYGON((1 2, oops))') is null"))
        .isEqualTo("t");
    assertThat(
            one(
                "select area.boundary_from_utmk_wkt('LINESTRING(953700 1954605, 953800 1954605)') is null"))
        .isEqualTo("t");
  }

  @Test
  void addressPointsAreKeyedBySourceIdAndSearchableByName() throws Exception {
    assertThat(
            one(
                "select a.attname from pg_index i join pg_attribute a"
                    + " on a.attrelid = i.indrelid and a.attnum = any(i.indkey)"
                    + " where i.indrelid = 'area.address_points'::regclass and i.indisprimary"))
        .isEqualTo("address_id");
    assertThat(
            one(
                "select string_agg(indexname, ',' order by indexname) from pg_indexes"
                    + " where schemaname = 'area' and tablename = 'address_points'"))
        .isEqualTo("address_points_name_idx,address_points_pkey,address_points_scope_idx");
  }

  @Test
  void utmKCoordinatesTransformToWgs84() throws Exception {
    // 도로명주소 원천 좌표는 UTM-K(EPSG:5179). 서울시청 근처 점이 경위도로 바뀌는지.
    assertThat(
            one(
                "select round(st_y(p)::numeric, 2) || ',' || round(st_x(p)::numeric, 2) from"
                    + " (select st_transform(st_setsrid(st_makepoint(953898, 1952036), 5179), 4326) p) t"))
        .isEqualTo("37.57,126.98");
  }

  @Test
  void industryGroupRulesAreSeeded() throws Exception {
    assertThat(
            one(
                "select industry_group from area.industry_group_rules where code_prefix = 'G20405'"))
        .isEqualTo("CONVENIENCE_STORE");
  }
}
