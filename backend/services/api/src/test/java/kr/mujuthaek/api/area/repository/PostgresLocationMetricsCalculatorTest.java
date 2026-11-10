package kr.mujuthaek.api.area.repository;

import static kr.mujuthaek.api.area.AreaTestDatabase.exec;
import static kr.mujuthaek.api.area.AreaTestDatabase.one;
import static org.assertj.core.api.Assertions.assertThat;

import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.area.AreaTestDatabase;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

/**
 * 세권 지표 계산이 맞는지. 시험 시설은 다른 테스트의 자료와 겹치지 않게 바다 위(북위 34.0, 동경 125.0 근처)에 놓아요.
 *
 * <p>가장 가까운 거리·반경 안 수는 인덱스 없이 전부 훑어 구한 값과 같아야 해요(정답 비교). 다른 테스트가 넣은 시설이 있어도 양쪽이 같은 자료를 보니 비교는 그대로
 * 맞아요.
 */
class PostgresLocationMetricsCalculatorTest {

  private static final String SOURCE = "TEST_METRICS";
  private static final PostgresLocationMetricsCalculator calculator =
      new PostgresLocationMetricsCalculator(AreaTestDatabase.dataSource());
  private static final List<UUID> locations = new ArrayList<>();

  @BeforeAll
  static void seed() throws Exception {
    cleanUp();
    // 시드를 고정한 가짜 분포: 5km 상자 안에 시설·상가, 같은 상자 안에 시험 위치 30곳
    exec(
        "select setseed(0.42);"
            + facilities("SUBWAY_STATION", "'1호선'", 40)
            + facilities("BUS_STOP", "null", 80)
            + facilities("SCHOOL", "'ELEMENTARY'", 20)
            + facilities("SCHOOL", "'MIDDLE'", 20)
            + facilities("SCHOOL", "'HIGH'", 20)
            + facilities("HOSPITAL", "'SECONDARY'", 15)
            + facilities("HOSPITAL", "'CLINIC'", 40)
            + "insert into area.facilities (kind, sub_kind, name, geom, extra, source, source_key,"
            + " data_date) select 'PARK', '근린공원', '공원' || i, "
            + point()
            + ", jsonb_build_object('area_m2', (1000 + random() * 50000)::int), '"
            + SOURCE
            + "', 'PARK-' || i, date '2026-09-30' from generate_series(1, 20) i;"
            + "insert into area.stores (source_key, load_scope, name, industry_group, geom,"
            + " data_date) select '"
            + SOURCE
            + "-' || i, '"
            + SOURCE
            + "', '점포' || i, (array['CONVENIENCE_STORE', 'MART', 'FOOD', 'CAFE'])[1 + i % 4], "
            + point()
            + ", date '2026-09-30' from generate_series(1, 400) i;"
            + "insert into area.notice_locations (location_id, notice_id, notice_location_id, notice_version, kind,"
            + " address_text, geom, status, method) select gen_random_uuid(), gen_random_uuid(), 'loc-' || i, 1,"
            + " 'COMPLEX', '시험 위치 ' || i, "
            + point()
            + ", 'OK', 'FILE' from generate_series(1, 30) i;"
            + "analyze area.facilities; analyze area.stores;");
    for (String id :
        one("select string_agg(location_id::text, ',' order by address_text)"
                + " from area.notice_locations where address_text ~ '^시험 위치 [0-9]+$'")
            .split(",")) {
      locations.add(UUID.fromString(id));
    }
  }

  @AfterAll
  static void cleanUp() throws Exception {
    exec("delete from area.facilities where source = '" + SOURCE + "'");
    exec("delete from area.stores where load_scope = '" + SOURCE + "'");
    exec("delete from area.notice_locations where address_text like '시험 위치%'");
    locations.clear();
  }

  @Test
  void nearestDistancesAndCountsMatchFullScan() throws Exception {
    calculator.calculate(locations);

    assertThat(
            mismatches(
                "station_nearest_m", nearest("area.facilities f", "f.kind = 'SUBWAY_STATION'")))
        .isZero();
    assertThat(
            mismatches(
                "hospital_nearest_m",
                nearest("area.facilities f", "f.kind = 'HOSPITAL' and f.sub_kind = 'SECONDARY'")))
        .isZero();
    assertThat(mismatches("mart_nearest_m", nearest("area.stores f", "f.industry_group = 'MART'")))
        .isZero();
    assertThat(
            mismatches(
                "store_count_300m",
                "(select count(*) from area.stores f where st_distance(f.geom, l.geom) <= 300)"))
        .isZero();
    assertThat(
            mismatches(
                "clinic_count_500m",
                "(select count(*) from area.facilities f where f.kind = 'HOSPITAL'"
                    + " and f.sub_kind = 'CLINIC' and st_distance(f.geom, l.geom) <= 500)"))
        .isZero();
    // 30곳 모두 지표 14개
    assertThat(one("select count(*) from area.location_metrics where location_id in " + ids()))
        .isEqualTo(String.valueOf(30 * 14));
  }

  @Test
  void transferStationCountsOnceByName() throws Exception {
    UUID at = UUID.randomUUID();
    // 바다 위 다른 곳: 같은 이름 3노선(약 200m), 다른 역(약 600m), 먼 역(약 1.5km)
    exec(
        "insert into area.facilities (kind, sub_kind, name, geom, source, source_key, data_date)"
            + " values"
            + station("1호선", "환승역", 0.0018, "T1")
            + ","
            + station("2호선", "환승역", 0.0018, "T2")
            + ","
            + station("3호선", "환승역", 0.0019, "T3")
            + ","
            + station("1호선", "다른역", 0.0054, "T4")
            + ","
            + station("1호선", "먼역", 0.0135, "T5"));
    exec(
        "insert into area.notice_locations (location_id, notice_id, notice_location_id, notice_version, kind,"
            + " address_text, geom, status, method) values ('"
            + at
            + "', gen_random_uuid(), 'building-a', 1, 'COMPLEX', '시험 위치 환승',"
            + " st_makepoint(125.5, 34.5)::geography, 'OK', 'FILE')");

    calculator.calculate(List.of(at));

    assertThat(metric(at, "station_count_1km")).isEqualTo("2");
  }

  @Test
  void nearestUsesSpheroidDistanceEvenWhenKnnOrderDiffers() throws Exception {
    // <->(KNN)는 구면 거리로 순서를 정하고 st_distance는 타원체 거리예요. 이 위도에서 구면은 남북을 조금 길게, 동서를 조금 짧게 재서
    // 타원체로 북쪽 1,000m 역보다 동쪽 1,001m 역이 <->로는 먼저 나와요(실제 자료 3,000곳 중 9곳, 최대 164m가 이렇게 틀렸음).
    UUID at = UUID.randomUUID();
    String p = "st_makepoint(124.5, 33.2)::geography";
    exec(
        "insert into area.facilities (kind, sub_kind, name, geom, source, source_key, data_date)"
            + " values ('SUBWAY_STATION', '1호선', '북쪽역', st_project("
            + p
            + ", 1000, 0), '"
            + SOURCE
            + "', 'SPH-N', date '2026-09-30'),"
            + " ('SUBWAY_STATION', '1호선', '동쪽역', st_project("
            + p
            + ", 1001, pi() / 2), '"
            + SOURCE
            + "', 'SPH-E', date '2026-09-30')");
    exec(
        "insert into area.notice_locations (location_id, notice_id, notice_location_id, notice_version, kind,"
            + " address_text, geom, status, method) values ('"
            + at
            + "', gen_random_uuid(), 'building-a', 1, 'COMPLEX', '시험 위치 구면', "
            + p
            + ", 'OK', 'FILE')");
    assertThat(
            one(
                "select name from area.facilities where kind = 'SUBWAY_STATION'"
                    + " order by geom <-> "
                    + p
                    + " limit 1"))
        .isEqualTo("동쪽역");

    calculator.calculate(List.of(at));

    assertThat(new java.math.BigDecimal(metric(at, "station_nearest_m")))
        .isCloseTo(
            new java.math.BigDecimal("1000"),
            org.assertj.core.data.Offset.offset(new java.math.BigDecimal("0.01")));
  }

  @Test
  void failedLocationGetsNoMetricsAndRerunReplacesRows() throws Exception {
    UUID failed = UUID.randomUUID();
    exec(
        "insert into area.notice_locations (location_id, notice_id, notice_location_id, notice_version, kind,"
            + " address_text, status, fail_reason) values ('"
            + failed
            + "', gen_random_uuid(), 'building-a', 1, 'COMPLEX', '시험 위치 실패', 'FAILED', 'NOT_FOUND')");
    List<UUID> targets = List.of(locations.get(0), failed);

    int first = calculator.calculate(targets);
    int second = calculator.calculate(targets);

    assertThat(first).isEqualTo(14);
    assertThat(second).isEqualTo(14);
    assertThat(
            one("select count(*) from area.location_metrics where location_id = '" + failed + "'"))
        .isEqualTo("0");
  }

  @Test
  void kindWithNoFacilitiesAnywhereLeavesMetricOut() throws Exception {
    // 다른 테스트의 자료를 건드리지 않게, 2차 병원을 지우고 계산하는 것까지 한 트랜잭션에서 하고 되돌려요.
    try (Connection c = AreaTestDatabase.dataSource().getConnection()) {
      c.setAutoCommit(false);
      try (Statement st = c.createStatement()) {
        st.execute(
            "delete from area.facilities where kind = 'HOSPITAL' and sub_kind = 'SECONDARY'");
        AreaCalcSql.fillTargets(c, List.of(locations.get(1)));
        st.execute(AreaCalcSql.read("metrics.sql"));
        try (ResultSet rs =
            st.executeQuery(
                "select string_agg(metric, ',') filter (where metric = 'hospital_nearest_m'),"
                    + " count(*) from area.location_metrics where location_id = '"
                    + locations.get(1)
                    + "'")) {
          rs.next();
          assertThat(rs.getString(1)).isNull();
          assertThat(rs.getInt(2)).isEqualTo(13);
        }
      } finally {
        c.rollback();
      }
    }
  }

  @Test
  void usesPartialIndexesWhoseConditionMatchesTheSql() throws Exception {
    // 계산 SQL의 where가 인덱스 조건과 글자 하나라도 다르면 부분 인덱스를 못 써요. 그러면 이 계획에서 이름이 빠져요.
    String sql = AreaCalcSql.read("metrics.sql");
    String insert =
        sql.substring(sql.indexOf("insert into area.location_metrics"), sql.lastIndexOf(';'));
    StringBuilder plan = new StringBuilder();
    try (Connection c = AreaTestDatabase.dataSource().getConnection()) {
      c.setAutoCommit(false);
      try (Statement st = c.createStatement()) {
        st.execute("set local enable_seqscan = off");
        AreaCalcSql.fillTargets(c, List.of(locations.get(2)));
        try (ResultSet rs = st.executeQuery("explain " + insert)) {
          while (rs.next()) {
            plan.append(rs.getString(1)).append('\n');
          }
        }
      } finally {
        c.rollback();
      }
    }
    assertThat(plan.toString())
        .contains(
            "facilities_subway_gix",
            "facilities_bus_gix",
            "facilities_school_gix",
            "facilities_park_gix",
            "facilities_hosp2_gix",
            "facilities_clinic_gix",
            "stores_conv_gix",
            "stores_mart_gix");
  }

  private static String point() {
    return "st_makepoint(125.0 + random() * 0.055, 34.0 + random() * 0.045)::geography";
  }

  private static String facilities(String kind, String subKind, int n) {
    return "insert into area.facilities (kind, sub_kind, name, geom, source, source_key,"
        + " data_date) select '"
        + kind
        + "', "
        + subKind
        + ", '"
        + kind
        + "' || i, "
        + point()
        + ", '"
        + SOURCE
        + "', '"
        + kind
        + "-' || coalesce("
        + subKind
        + ", '') || '-' || i, date '2026-09-30' from generate_series(1, "
        + n
        + ") i;";
  }

  private static String station(String line, String name, double dLat, String key) {
    return "('SUBWAY_STATION', '"
        + line
        + "', '"
        + name
        + "', st_makepoint(125.5, "
        + (34.5 + dLat)
        + ")::geography, '"
        + SOURCE
        + "', '"
        + key
        + "', date '2026-09-30')";
  }

  private static String nearest(String from, String where) {
    return "(select st_distance(f.geom, l.geom) from "
        + from
        + " where "
        + where
        + " order by st_distance(f.geom, l.geom) limit 1)";
  }

  /** 저장된 지표와 전부 훑어 구한 값이 다른 위치 수. */
  private static int mismatches(String metric, String fullScan) throws Exception {
    return Integer.parseInt(
        one(
            "select count(*) from area.notice_locations l"
                + " left join area.location_metrics m on m.location_id = l.location_id"
                + " and m.metric = '"
                + metric
                + "' where l.location_id in "
                + ids()
                + " and m.value is distinct from ("
                + fullScan
                + ")::numeric"));
  }

  private static String metric(UUID location, String metric) throws Exception {
    return one(
        "select value from area.location_metrics where location_id = '"
            + location
            + "' and metric = '"
            + metric
            + "'");
  }

  private static String ids() {
    StringBuilder sb = new StringBuilder("(");
    for (UUID id : locations) {
      sb.append(sb.length() > 1 ? "," : "").append('\'').append(id).append('\'');
    }
    return sb.append(')').toString();
  }
}
