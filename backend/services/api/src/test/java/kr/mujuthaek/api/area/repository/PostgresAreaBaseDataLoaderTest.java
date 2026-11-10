package kr.mujuthaek.api.area.repository;

import static kr.mujuthaek.api.area.AreaTestDatabase.exec;
import static kr.mujuthaek.api.area.AreaTestDatabase.one;
import static org.assertj.core.api.Assertions.assertThat;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.LocalDate;
import java.util.HexFormat;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.api.area.AreaTestDatabase;
import kr.mujuthaek.api.area.domain.AreaLoadReport;
import kr.mujuthaek.api.area.domain.AreaLoadRequest;
import kr.mujuthaek.api.area.domain.AreaSource;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/** 실제 PostGIS에 마이그레이션을 적용하고, 원천 파일과 같은 인코딩(CP949·UTF-8)의 자료로 적재해요. */
class PostgresAreaBaseDataLoaderTest {

  private final PostgresAreaBaseDataLoader loader =
      new PostgresAreaBaseDataLoader(AreaTestDatabase.dataSource());

  @BeforeEach
  void clean() throws Exception {
    exec(
        "truncate area.facilities, area.stores, area.address_points, area.region_boundaries,"
            + " area.road_names,"
            + " area.load_runs");
  }

  @Test
  void busStops_rejectsBadRows_fixesSwappedCoordinates_skipsBlankLines() throws Exception {
    AreaLoadReport r = load(AreaSource.BUS_STOP, "ALL", "bus_stop.csv", false);

    assertThat(r.status()).isEqualTo(AreaLoadReport.Status.SUCCEEDED);
    assertThat(r.rowsIn()).isEqualTo(8);
    assertThat(r.rowsInserted()).isEqualTo(3);
    assertThat(r.rowsFixed()).isEqualTo(1);
    assertThat(r.rejectReasons())
        .isEqualTo(Map.of("NO_COORD", 2, "OUT_OF_RANGE", 1, "DUPLICATE_KEY", 1, "NO_KEY", 1));
    assertThat(
            one(
                "select round(st_y(geom::geometry)::numeric,4)||','||round(st_x(geom::geometry)::numeric,4) "
                    + "from area.facilities where source_key='SWAP0001'"))
        .isEqualTo("37.5665,126.9780");
    assertThat(one("select substring(id::text,15,1) from area.facilities limit 1")).isEqualTo("7");
    assertThat(one("select status from area.load_runs")).isEqualTo("SUCCEEDED");
  }

  @Test
  void loadRun_continuesTheQueuedRun_andSkipsItWhenTheFileAlreadySucceeded() throws Exception {
    LocalDate date = LocalDate.of(2026, 6, 30);
    var req =
        new AreaLoadRequest(AreaSource.BUS_STOP, "ALL", "area/x.csv", "q".repeat(64), date, false);
    UUID first = UUID.fromString("01a00000-0000-7000-8000-000000000001");
    UUID second = UUID.fromString("01a00000-0000-7000-8000-000000000002");
    exec(runningRow(first));

    AreaLoadReport r;
    try (InputStream in = Files.newInputStream(fixture("bus_stop.csv"))) {
      r = loader.loadRun(first, req, in);
    }
    assertThat(r.runId()).isEqualTo(first);
    assertThat(r.status()).isEqualTo(AreaLoadReport.Status.SUCCEEDED);

    // 같은 파일 요청이 그사이 또 꺼내졌어도 이미 성공했으니 건너뛰어요
    exec(runningRow(second));
    try (InputStream in = Files.newInputStream(fixture("bus_stop.csv"))) {
      assertThat(loader.loadRun(second, req, in).status()).isEqualTo(AreaLoadReport.Status.SKIPPED);
    }
    assertThat(one("select string_agg(status, ',' order by id) from area.load_runs"))
        .isEqualTo("SUCCEEDED,SKIPPED");
  }

  @Test
  void subwayStations_keepLineAsSubKind() throws Exception {
    AreaLoadReport r = load(AreaSource.SUBWAY_STATION, "ALL", "subway_station.csv", false);

    assertThat(r.rowsInserted()).isEqualTo(2);
    assertThat(
            one(
                "select string_agg(name||':'||sub_kind, ',' order by source_key) from area.facilities"))
        .isEqualTo("신사:신분당선,논현:신분당선");
  }

  @Test
  void schoolsParksHospitals_followFilterRules() throws Exception {
    assertThat(load(AreaSource.SCHOOL, "ALL", "school.csv", false).rowsInserted()).isEqualTo(2);
    assertThat(
            one(
                "select string_agg(sub_kind, ',' order by sub_kind) from area.facilities where kind='SCHOOL'"))
        .isEqualTo("ELEMENTARY,HIGH");
    assertThat(load(AreaSource.PARK, "ALL", "park.csv", false).rowsInserted()).isEqualTo(2);
    assertThat(
            one(
                "select string_agg(extra->>'area_m2', ',' order by (extra->>'area_m2')::numeric) "
                    + "from area.facilities where kind='PARK'"))
        .isEqualTo("1400,189000");
    AreaLoadReport h = load(AreaSource.HOSPITAL, "ALL", "hospital.csv", false);
    assertThat(h.rowsInserted()).isEqualTo(3);
    assertThat(h.rowsSkipped()).isEqualTo(2);
    assertThat(
            one(
                "select string_agg(sub_kind, ',' order by sub_kind) from area.facilities where kind='HOSPITAL'"))
        .isEqualTo("CLINIC,CLINIC,SECONDARY");
  }

  @Test
  void missingColumn_failsAndKeepsPreviousData() throws Exception {
    load(AreaSource.HOSPITAL, "ALL", "hospital.csv", false);
    AreaLoadReport r = load(AreaSource.HOSPITAL, "ALL", "hospital_no_coord_column.csv", false);

    assertThat(r.status()).isEqualTo(AreaLoadReport.Status.FAILED);
    assertThat(r.error()).contains("좌표(X)");
    assertThat(one("select count(*) from area.facilities where kind='HOSPITAL'")).isEqualTo("3");
    assertThat(one("select count(*) from area.load_runs where status='FAILED'")).isEqualTo("1");
  }

  @Test
  void loadingTheSameSourceAgain_keepsUnchangedRows() throws Exception {
    load(AreaSource.SCHOOL, "ALL", "school.csv", false);
    exec("delete from area.load_runs");
    AreaLoadReport again = load(AreaSource.SCHOOL, "ALL", "school.csv", false);

    assertThat(again.rowsInserted()).isZero();
    assertThat(again.rowsUpdated()).isZero();
    assertThat(again.rowsUnchanged()).isEqualTo(2);
    assertThat(again.changedData()).isFalse();
  }

  @Test
  void newDataDateWithSameRows_leavesRowsUntouched() throws Exception {
    // 같은 내용을 기준일만 바꿔 다시 받으면(지문은 달라서 SKIPPED가 아님) 줄은 그대로, 원천 기준일은 적재 기록에만
    load(
        loader,
        AreaSource.STORES,
        "강원",
        "stores_gangwon.csv",
        "a".repeat(64),
        LocalDate.of(2026, 6, 30),
        false);
    AreaLoadReport again =
        load(
            loader,
            AreaSource.STORES,
            "강원",
            "stores_gangwon.csv",
            "b".repeat(64),
            LocalDate.of(2026, 9, 30),
            false);

    assertThat(again.status()).isEqualTo(AreaLoadReport.Status.SUCCEEDED);
    assertThat(again.rowsUnchanged()).isEqualTo(7);
    assertThat(again.rowsInserted() + again.rowsUpdated() + again.rowsDeleted()).isZero();
    assertThat(one("select string_agg(distinct data_date::text, ',') from area.stores"))
        .isEqualTo("2026-06-30");
    assertThat(
            one("select string_agg(data_date::text, ',' order by started_at) from area.load_runs"))
        .isEqualTo("2026-06-30,2026-09-30");
  }

  @Test
  void sameFileTwice_isSkipped() throws Exception {
    load(AreaSource.BUS_STOP, "ALL", "bus_stop.csv", false);
    AreaLoadReport again = load(AreaSource.BUS_STOP, "ALL", "bus_stop.csv", false);

    assertThat(again.status()).isEqualTo(AreaLoadReport.Status.SKIPPED);
    assertThat(one("select string_agg(status, ',' order by started_at) from area.load_runs"))
        .isEqualTo("SUCCEEDED,SKIPPED");
  }

  @Test
  void sameFileForAnotherScope_isLoaded() throws Exception {
    load(AreaSource.STORES, "강원", "stores_gangwon.csv", false);
    // 같은 지문이라도 범위(시도)가 다르면 다른 적재예요.
    assertThat(load(AreaSource.STORES, "경기", "stores_gangwon.csv", false).status())
        .isEqualTo(AreaLoadReport.Status.SUCCEEDED);
  }

  @Test
  void stores_refillNationalIndustryShares() throws Exception {
    load(AreaSource.STORES, "강원", "stores_gangwon.csv", false);

    // 입지계수의 분모: 업종 묶음별 전국 점포 수와 그때 전체 점포 수
    assertThat(
            one(
                "select string_agg(industry||':'||store_count||'/'||total_count, ',' order by industry)"
                    + " from area.industry_shares"))
        .isEqualTo(
            one(
                "select 'CAFE:'||count(*) filter (where industry_group = 'CAFE')||'/'||count(*)"
                    + "||',FOOD:'||count(*) filter (where industry_group = 'FOOD')||'/'||count(*)"
                    + "||',RETAIL:'||count(*) filter (where large_code = 'G2')||'/'||count(*)"
                    + " from area.stores"));
  }

  @Test
  void shrinkGuard_stopsTruncatedFiles() throws Exception {
    load(AreaSource.BUS_STOP, "ALL", "bus_stop_150.csv", false);
    AreaLoadReport blocked = load(AreaSource.BUS_STOP, "ALL", "bus_stop_small.csv", false);
    assertThat(blocked.status()).isEqualTo(AreaLoadReport.Status.FAILED);
    assertThat(blocked.error()).contains("절반");
    assertThat(one("select count(*) from area.facilities where source='BUS_STOP'"))
        .isEqualTo("150");

    AreaLoadReport allowed = load(AreaSource.BUS_STOP, "ALL", "bus_stop_small.csv", true);
    assertThat(allowed.rowsDeleted()).isEqualTo(140);
    assertThat(allowed.rowsUnchanged()).isEqualTo(10);
  }

  @Test
  void stores_groupIndustries_andDeleteOnlyWithinScope() throws Exception {
    assertThat(load(AreaSource.STORES, "강원", "stores_gangwon.csv", false).rowsInserted())
        .isEqualTo(7);
    assertThat(
            one(
                "select string_agg(industry_group||':'||name, ',' order by source_key) from area.stores"))
        .isEqualTo(
            "CONVENIENCE_STORE:GS25 춘천점,MART:동네슈퍼,CAFE:커피집,R1:스터디카페,FOOD:닭갈비집,BAR:호프,P1:수학학원");

    AreaLoadReport gyeonggi = load(AreaSource.STORES, "경기", "stores_gyeonggi.csv", false);
    assertThat(gyeonggi.rowsDeleted()).isZero();
    assertThat(one("select count(*) from area.stores where load_scope='강원'")).isEqualTo("7");
  }

  @Test
  void stores_realHeaderWithAllCellsQuoted() throws Exception {
    // 실제 상가정보 파일(강원 2026-06)의 머리줄 39칸(모두 따옴표)과 실제 한 줄 그대로예요.
    AreaLoadReport r = load(AreaSource.STORES, "강원", "stores_real_header.csv", false);

    assertThat(r.status()).isEqualTo(AreaLoadReport.Status.SUCCEEDED);
    assertThat(r.rowsInserted()).isEqualTo(1);
    assertThat(
            one(
                "select name||'|'||small_code||'|'||industry_group||'|'||address||'|'"
                    + "||round(st_y(geom::geometry)::numeric,4)||','||round(st_x(geom::geometry)::numeric,4)"
                    + " from area.stores"))
        .isEqualTo("파크랜드춘천 명동점|G21304|G2|강원특별자치도 춘천시 금강로 80|37.8783,127.7295");
  }

  @Test
  void addressEntrance_headerlessPipeFileInUtmK() throws Exception {
    // 부산 실제 3줄 + 좌표 글자·번호 오류·키 중복·범위 밖·값 안 따옴표+지하 줄, 끝 빈 줄, CRLF (CP949)
    AreaLoadReport r = load(AreaSource.ADDRESS_ENTRANCE, "26", "address_entrance_26.txt", false);

    assertThat(r.status()).isEqualTo(AreaLoadReport.Status.SUCCEEDED);
    assertThat(r.rowsIn()).isEqualTo(8);
    assertThat(r.rowsInserted()).isEqualTo(4);
    assertThat(r.rejectReasons())
        .isEqualTo(Map.of("NO_COORD", 1, "BAD_NUMBER", 1, "DUPLICATE_KEY", 1, "OUT_OF_RANGE", 1));
    // UTM-K → 경위도: 초량상로 1-2
    assertThat(
            one(
                "select round(st_y(geom::geometry)::numeric,5)||','||round(st_x(geom::geometry)::numeric,5)"
                    + " from area.address_points where address_id = '26110101300600100000100002'"))
        .isEqualTo("35.11243,129.03502");
    // 공고 주소처럼 시군구 + 도로명 + 번호로 찾기
    assertThat(
            one(
                "select address_id from area.address_points where sigungu_code = '26110'"
                    + " and road_name = '초량상로' and underground = 0 and bldg_main = 5 and bldg_sub = 0"))
        .isEqualTo("26110101300600100000500000");
    // 값 안의 따옴표는 그대로, 지하 주소
    assertThat(
            one(
                "select road_name||'|'||underground||'|'||bldg_main from area.address_points"
                    + " where address_id = '26110101300600100001300000'"))
        .isEqualTo("\"초량\"상로|1|13");
  }

  @Test
  void addressEntrance_acceptsUndergroundCode3() throws Exception {
    // 경남 통영 실제 2줄: 산양일주로 1461-132는 지하여부 3, 산양일주로 46은 0
    AreaLoadReport r = load(AreaSource.ADDRESS_ENTRANCE, "48", "address_entrance_48.txt", false);

    assertThat(r.rowsRejected()).isZero();
    assertThat(r.rowsInserted()).isEqualTo(2);
    assertThat(
            one(
                "select road_name||'|'||underground||'|'||bldg_main||'-'||bldg_sub"
                    + " from area.address_points where address_id = '48220250333301430146100132'"))
        .isEqualTo("산양일주로|3|1461-132");
    assertThat(
            one(
                "select col_description('area.address_points'::regclass, attnum) from pg_attribute"
                    + " where attrelid = 'area.address_points'::regclass and attname = 'underground'"))
        .contains("지하");
  }

  @Test
  void regionBoundaries_transformFromUtmkFixShapesAndRejectBadRows() throws Exception {
    AreaLoadReport r = load(AreaSource.REGION_BOUNDARY_SIG, "ALL", "boundary_sig.csv", false);

    assertThat(r.status()).isEqualTo(AreaLoadReport.Status.SUCCEEDED);
    assertThat(r.rowsInserted()).isEqualTo(3);
    assertThat(r.rejectReasons()).isEqualTo(Map.of("BAD_CODE", 1, "BAD_GEOMETRY", 1));
    assertThat(
            one(
                "select string_agg(code || ':' || st_numgeometries(geom::geometry), ',' order by code)"
                    + " from area.region_boundaries where level = 'SIG'"))
        .isEqualTo("11110:1,11140:2,11200:2"); // 꼬인 고리(성동구)는 고쳐서 두 조각
    // UTM-K → 경위도 (청운동 근처)
    assertThat(
            one(
                "select round(st_y(st_centroid(geom::geometry))::numeric, 2) || ','"
                    + " || round(st_x(st_centroid(geom::geometry))::numeric, 2)"
                    + " from area.region_boundaries where code = '11110'"))
        .isEqualTo("37.59,126.97");
  }

  @Test
  void regionBoundaries_reloadKeepsSameRowsAndLevelsStaySeparate() throws Exception {
    load(AreaSource.REGION_BOUNDARY_SIG, "ALL", "boundary_sig.csv", false);
    AreaLoadReport emd = load(AreaSource.REGION_BOUNDARY_EMD, "ALL", "boundary_emd.csv", false);
    AreaLoadReport again =
        load(
            loader,
            AreaSource.REGION_BOUNDARY_SIG,
            "ALL",
            "boundary_sig.csv",
            "e".repeat(64),
            LocalDate.of(2026, 10, 22),
            false);

    assertThat(emd.rowsInserted()).isEqualTo(1);
    assertThat(emd.rowsDeleted()).isZero(); // 법정읍면동 적재가 시군구를 지우지 않음
    assertThat(again.rowsUnchanged()).isEqualTo(3);
    assertThat(again.rowsUpdated()).isZero();
    assertThat(one("select count(*) from area.region_boundaries")).isEqualTo("4");
  }

  @Test
  void addressEntrance_deletesOnlyWithinSidoCode() throws Exception {
    load(AreaSource.ADDRESS_ENTRANCE, "26", "address_entrance_26.txt", false);
    AreaLoadReport seoul =
        load(AreaSource.ADDRESS_ENTRANCE, "11", "address_entrance_11.txt", false);

    assertThat(seoul.rowsInserted()).isEqualTo(1);
    assertThat(seoul.rowsDeleted()).isZero();
    assertThat(one("select count(*) from area.address_points where load_scope = '26'"))
        .isEqualTo("4");
    // 서울시청
    assertThat(
            one(
                "select round(st_y(geom::geometry)::numeric,4)||','||round(st_x(geom::geometry)::numeric,3)"
                    + " from area.address_points where load_scope = '11'"))
        .isEqualTo("37.5665,126.978");
  }

  @Test
  void addressEntrance_refillsRoadNamesOfThatSidoOnly() throws Exception {
    load(AreaSource.ADDRESS_ENTRANCE, "26", "address_entrance_26.txt", false);
    load(AreaSource.ADDRESS_ENTRANCE, "11", "address_entrance_11.txt", false);
    String names =
        "select string_agg(n, ',' order by n) from (select sigungu_code||':'||road_name n from area.road_names) d";
    String fromAddresses =
        "select string_agg(n, ',' order by n) from (select distinct sigungu_code||':'||road_name n"
            + " from area.address_points) d";
    assertThat(one(names)).isEqualTo(one(fromAddresses));

    // 부산을 다시 넣으면 부산의 옛 도로명은 지워지고 서울 것은 그대로예요
    exec("insert into area.road_names values ('26110', '옛길'), ('11140', '서울옛길')");
    load(
        loader,
        AreaSource.ADDRESS_ENTRANCE,
        "26",
        "address_entrance_26.txt",
        "e".repeat(64),
        LocalDate.of(2026, 10, 22),
        false);
    assertThat(one("select count(*) from area.road_names where road_name = '옛길'")).isEqualTo("0");
    assertThat(one("select count(*) from area.road_names where road_name = '서울옛길'")).isEqualTo("1");
  }

  @Test
  void addressEntrance_updatesRowsWhoseEupMyeonDongNameChanged() throws Exception {
    load(AreaSource.ADDRESS_ENTRANCE, "26", "address_entrance_26.txt", false);
    exec(
        "update area.address_points set emd = '옛이름'"
            + " where address_id = '26110101300600100000100002'");

    AreaLoadReport again =
        load(
            loader,
            AreaSource.ADDRESS_ENTRANCE,
            "26",
            "address_entrance_26.txt",
            "f".repeat(64),
            LocalDate.of(2026, 10, 22),
            false);

    assertThat(again.rowsUpdated()).isEqualTo(1);
    assertThat(again.rowsUnchanged()).isEqualTo(3);
    assertThat(
            one(
                "select emd from area.address_points"
                    + " where address_id = '26110101300600100000100002'"))
        .isNotEqualTo("옛이름");
  }

  private static String runningRow(UUID id) {
    return "insert into area.load_runs (id, source, load_scope, file_key, file_sha256, data_date, status)"
        + " values ('"
        + id
        + "', 'BUS_STOP', 'ALL', 'area/x.csv', '"
        + "q".repeat(64)
        + "', date '2026-06-30', 'RUNNING')";
  }

  static AreaLoadReport load(
      PostgresAreaBaseDataLoader loader,
      AreaSource source,
      String scope,
      String file,
      boolean allowShrink)
      throws Exception {
    Path path = fixture(file);
    String sha =
        HexFormat.of()
            .formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path)));
    return load(loader, source, scope, file, sha, LocalDate.of(2026, 10, 21), allowShrink);
  }

  /** 지문과 기준일을 직접 정해서 적재 (같은 파일을 다른 적재로 다시 넣을 때). */
  static AreaLoadReport load(
      PostgresAreaBaseDataLoader loader,
      AreaSource source,
      String scope,
      String file,
      String sha,
      LocalDate dataDate,
      boolean allowShrink)
      throws Exception {
    var req =
        new AreaLoadRequest(
            source,
            scope,
            "area/" + source + "/" + dataDate + "/" + file,
            sha,
            dataDate,
            allowShrink);
    try (InputStream in = Files.newInputStream(fixture(file))) {
      return loader.load(req, in);
    }
  }

  static Path fixture(String name) throws Exception {
    return Path.of(
        PostgresAreaBaseDataLoaderTest.class
            .getClassLoader()
            .getResource("area/fixtures/" + name)
            .toURI());
  }

  private AreaLoadReport load(AreaSource source, String scope, String file, boolean allowShrink)
      throws Exception {
    return load(loader, source, scope, file, allowShrink);
  }
}
