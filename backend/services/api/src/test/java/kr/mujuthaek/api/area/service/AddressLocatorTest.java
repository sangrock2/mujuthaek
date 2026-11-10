package kr.mujuthaek.api.area.service;

import static kr.mujuthaek.api.area.AreaTestDatabase.exec;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;
import kr.mujuthaek.api.area.AreaTestDatabase;
import kr.mujuthaek.api.area.domain.GeocodeResult;
import kr.mujuthaek.api.area.domain.GeocodeResult.FailReason;
import kr.mujuthaek.api.area.domain.GeocodeResult.Method;
import kr.mujuthaek.api.area.domain.GeocodeResult.Status;
import kr.mujuthaek.api.area.geocode.CoordOutcome;
import kr.mujuthaek.api.area.geocode.JusoResult;
import kr.mujuthaek.api.area.geocode.SearchOutcome;
import kr.mujuthaek.api.area.geocode.SearchOutcome.Failed;
import kr.mujuthaek.api.area.geocode.SearchOutcome.Found;
import kr.mujuthaek.api.area.geocode.SearchOutcome.NotFound;
import kr.mujuthaek.api.area.geocode.SearchOutcome.Reason;
import kr.mujuthaek.api.area.repository.PostgresAddressPointLookup;
import kr.mujuthaek.api.area.repository.PostgresLegalDongCentroid;
import kr.mujuthaek.api.area.repository.PostgresRegionBoundaryCheck;
import kr.mujuthaek.api.area.repository.PostgresUtmkTransform;
import kr.mujuthaek.api.common.region.RegionQueryService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * 주소 → 좌표 길마다 (사전 그대로·오타·검색 API → 사전·섬 주소·대표점·실패). 사전·경계·지역 코드표는 시험 줄을 직접 넣고, 검색 API는 가짜예요. 시험 시군구는
 * 부산광역시 아래 가짜 「시험구」(26990)라 실제 자료와 섞이지 않아요(주소 정리는 실제 시도 이름만 알아봐요).
 */
class AddressLocatorTest {

  private static final String BJD = "2699010100";

  private final List<String> searched = new ArrayList<>();
  private Function<String, SearchOutcome> answer = keyword -> new NotFound();
  // 좌표제공 API는 기본으로 키 없음 (승인 대기라 대부분 환경이 이래요)
  private Function<JusoResult, CoordOutcome> coordAnswer =
      building -> new CoordOutcome.Failed(Reason.NO_KEY, null);
  private final AddressLocator locator =
      new AddressLocator(
          new PostgresAddressPointLookup(AreaTestDatabase.dataSource()),
          keyword -> {
            searched.add(keyword);
            return answer.apply(keyword);
          },
          building -> coordAnswer.apply(building),
          new PostgresUtmkTransform(AreaTestDatabase.dataSource()),
          new PostgresLegalDongCentroid(AreaTestDatabase.dataSource()),
          new PostgresRegionBoundaryCheck(AreaTestDatabase.dataSource()),
          new RegionQueryService(new JdbcTemplate(AreaTestDatabase.dataSource())));

  @BeforeEach
  void data() throws Exception {
    exec("delete from area.address_points where load_scope = '99'");
    exec("delete from area.road_names where sigungu_code = '26990'");
    exec("delete from area.region_boundaries where code in ('26990101', '26990')");
    exec("delete from common.region_code_changes where old_code = '2698010100'");
    exec(
        "insert into common.regions (code, level, parent_code, name, full_name, short_name, base_date)"
            + " values ('26', 'SIDO', null, '부산광역시', '부산광역시', '부산', date '2026-09-29')"
            + " on conflict do nothing");
    exec(
        "insert into common.regions (code, level, parent_code, name, full_name, base_date)"
            + " values ('26990', 'SIGUNGU', '26', '시험구', '부산광역시 시험구', date '2026-09-29')"
            + " on conflict do nothing");
    exec(
        "insert into common.region_code_changes values ('2698010100', '2699010100', date '2026-09-29')");
    address("초량상로", 0, 1, 2, "a1", 129.04, 35.10);
    address("산양일주로", 3, 700, 0, "a2", 129.05, 35.11); // 섬 주소: 원천 지하 여부 3
    address("초량중앙상로", 0, 3, 0, "a3", 129.06, 35.12);
    exec(
        "insert into area.road_names select distinct sigungu_code, road_name from area.address_points"
            + " where load_scope = '99'");
    exec(
        "insert into area.region_boundaries (level, code, name, geom, data_date) values ('EMD', '26990101',"
            + " '시험동', 'SRID=4326;MULTIPOLYGON(((129.00 35.00, 129.02 35.00, 129.02 35.02, 129.00 35.02,"
            + " 129.00 35.00)))'::geography, date '2026-09-30')");
  }

  @Test
  void roadAddressInTheDictionaryNeedsNoSearch() {
    GeocodeResult r = locator.locate("부산광역시 시험구 초량상로 1-2", BJD);

    assertThat(r.status()).isEqualTo(Status.OK);
    assertThat(r.method()).isEqualTo(Method.FILE);
    assertThat(r.coordinate().lat()).isEqualTo(35.10);
    assertThat(r.bjdCodeFound()).isEqualTo(BJD);
    assertThat(r.sigunguCode()).isEqualTo("26990");
    assertThat(r.addressId()).isEqualTo(id("a1"));
    assertThat(searched).isEmpty();
  }

  @Test
  void aCoordinateOutsideTheSigunguBoundaryIsDropped() throws Exception {
    // 시험구 경계가 사전 좌표(129.04, 35.10)에서 멀리 있음: 사전 좌표가 틀렸거나 다른 시군구
    sigunguBoundary(128.00, 34.00);

    GeocodeResult r = locator.locate("부산광역시 시험구 초량상로 1-2", BJD);

    assertThat(r.status()).isEqualTo(Status.FAILED);
    assertThat(r.failReason()).isEqualTo(FailReason.OUT_OF_REGION);
    assertThat(r.coordinate()).isNull();
  }

  @Test
  void outsideTheGivenLegalDongIsOnlyMarked() throws Exception {
    // 시군구 경계 안이지만 받은 법정동(시험동 129.00~129.02) 밖
    sigunguBoundary(129.03, 35.09);

    GeocodeResult r = locator.locate("부산광역시 시험구 초량상로 1-2", BJD);

    assertThat(r.status()).isEqualTo(Status.OK);
    assertThat(r.regionMismatch()).isTrue();
  }

  @Test
  void typoIsFixedInTheDictionary() {
    GeocodeResult r = locator.locate("부산광역시 시험구 초량중앙삼로 3", BJD);

    assertThat(r.method()).isEqualTo(Method.FUZZY);
    assertThat(r.addressId()).isEqualTo(id("a3"));
    assertThat(searched).isEmpty();
  }

  @Test
  void aTypoInTheRoadSuffixIsNotARoadSoItIsTheRepresentativePoint() {
    // 끝 글자(로·길) 오타는 주소 정리가 도로명으로 보지 않아요(지역만 있는 주소) → 검색 API를 부르지 않고 대표점
    GeocodeResult r = locator.locate("부산광역시 시험구 초량상노 1-2", BJD);

    assertThat(r.status()).isEqualTo(Status.APPROX);
    assertThat(searched).isEmpty();
  }

  @Test
  void unknownRoadNameGoesThroughTheSearchApiBackToTheDictionary() {
    answer = keyword -> found(juso("초량상로", "0", "1", "2"));

    GeocodeResult r = locator.locate("부산광역시 시험구 옛이름대로 1-2", BJD);

    assertThat(r.status()).isEqualTo(Status.OK);
    assertThat(r.method()).isEqualTo(Method.SEARCH_API);
    assertThat(r.addressId()).isEqualTo(id("a1"));
    assertThat(searched).hasSize(1);
  }

  @Test
  void jibunAddressGoesThroughTheSearchApi() {
    answer = keyword -> found(juso("초량상로", "0", "1", "2"));

    GeocodeResult r = locator.locate("부산광역시 시험구 시험동 100-1", BJD);

    assertThat(r.method()).isEqualTo(Method.SEARCH_API);
    assertThat(r.addressId()).isEqualTo(id("a1"));
  }

  @Test
  void islandAddressIsFoundWithoutTheUndergroundCode() {
    // 검색 API는 지하 여부를 0으로 주지만 사전에는 3
    answer = keyword -> found(juso("산양일주로", "0", "700", "0"));

    GeocodeResult r = locator.locate("부산광역시 시험구 시험동 산 5", BJD);

    assertThat(r.method()).isEqualTo(Method.SEARCH_API);
    assertThat(r.addressId()).isEqualTo(id("a2"));
  }

  @Test
  void manySearchResultsMeanTheRepresentativePointOfTheLegalDong() {
    answer = keyword -> found(juso("초량상로", "0", "1", "2"), juso("산양일주로", "0", "700", "0"));

    GeocodeResult r = locator.locate("부산광역시 시험구 시험동 100-1", BJD);

    assertThat(r.status()).isEqualTo(Status.APPROX);
    assertThat(r.method()).isEqualTo(Method.CENTROID);
    assertThat(r.bjdCodeFound()).isEqualTo(BJD);
    assertThat(r.coordinate().lat()).isBetween(35.00, 35.02);
    assertThat(r.addressId()).isNull();
  }

  @Test
  void aNewBuildingMissingFromTheDictionaryUsesTheCoordinateApi() {
    answer = keyword -> found(juso("새길", "0", "9", "0"));
    coordAnswer = building -> new CoordOutcome.Found(953901.165312, 1952032.080979); // UTM-K

    GeocodeResult r = locator.locate("부산광역시 시험구 새길 9", BJD);

    assertThat(r.status()).isEqualTo(Status.OK);
    assertThat(r.method()).isEqualTo(Method.COORD_API);
    assertThat(r.coordinate().lat()).isCloseTo(37.5665, within(0.0001)); // 경위도로 바뀜
    assertThat(r.bjdCodeFound()).isEqualTo(BJD);
    assertThat(r.addressId()).isNull(); // 사전 주소가 아니라 주소 ID가 없어요
  }

  @Test
  void coordinateApiTroubleWithoutARepresentativePointIsAnApiError() {
    // 검색 결과의 법정동에 경계가 없고 공고도 코드를 주지 않은 새 건물
    answer = keyword -> found(jusoAt("2699020100", "새길", "9"));
    coordAnswer = building -> new CoordOutcome.Failed(Reason.UNAVAILABLE, "-999");

    GeocodeResult r = locator.locate("부산광역시 시험구 새길 9", null);

    assertThat(r.failReason()).isEqualTo(FailReason.API_ERROR);
  }

  @Test
  void aBuildingMissingFromTheDictionaryUsesTheLegalDongTheSearchApiFound() {
    // 검색 API는 찾았는데 사전에 아직 없는 새 건물, 공고가 법정동코드를 주지 않은 경우
    answer = keyword -> found(juso("새길", "0", "9", "0"));

    GeocodeResult r = locator.locate("부산광역시 시험구 새길 9", null);

    assertThat(r.status()).isEqualTo(Status.APPROX);
    assertThat(r.bjdCodeFound()).isEqualTo(BJD);
    assertThat(r.sigunguCode()).isEqualTo("26990"); // 이름으로 찾은 시군구
  }

  @Test
  void withoutACodeTheLegalDongNameGivesTheRepresentativePoint() {
    // 공고가 법정동코드를 주지 않았고 검색 API도 못 찾은 지번 (건물 없는 개발 부지)
    GeocodeResult r = locator.locate("부산광역시 시험구 시험동 656-6", null);

    assertThat(r.status()).isEqualTo(Status.APPROX);
    assertThat(r.bjdCodeFound()).isEqualTo(BJD);
    assertThat(r.sigunguCode()).isEqualTo("26990");
    assertThat(searched).hasSize(1);
  }

  @Test
  void withoutASearchKeyTheStepIsSkippedNotAnError() {
    answer = keyword -> new Failed(Reason.NO_KEY, null);

    assertThat(locator.locate("부산광역시 시험구 없는길 5", BJD).status()).isEqualTo(Status.APPROX);
    assertThat(locator.locate("부산광역시 시험구 없는길 5", null).failReason())
        .isEqualTo(FailReason.NOT_FOUND);
  }

  @Test
  void searchApiTroubleWithoutAFallbackIsAnApiError() {
    answer = keyword -> new Failed(Reason.UNAVAILABLE, "-999");

    GeocodeResult r = locator.locate("부산광역시 시험구 없는길 5", null);

    assertThat(r.status()).isEqualTo(Status.FAILED);
    assertThat(r.failReason()).isEqualTo(FailReason.API_ERROR);
    assertThat(r.coordinate()).isNull();
    assertThat(r.sigunguCode()).isEqualTo("26990");
  }

  @Test
  void anOldLegalDongCodeIsChangedToTheCurrentOne() {
    GeocodeResult r = locator.locate("부산광역시 시험구 초량상로 1-2", "2698010100");

    assertThat(r.method()).isEqualTo(Method.FILE);
    assertThat(r.sigunguCode()).isEqualTo("26990");
  }

  @Test
  void textWithoutAnyAddressFails() {
    assertThat(locator.locate("주소 별도 안내", null).failReason()).isEqualTo(FailReason.PARSE_FAILED);
    assertThat(locator.locate(null, null).failReason()).isEqualTo(FailReason.PARSE_FAILED);
    assertThat(searched).isEmpty();
  }

  @Test
  void areaOnlyAddressWithACodeIsTheRepresentativePoint() {
    GeocodeResult r = locator.locate("부산광역시 시험구 ○○지구 A17블록", BJD);

    assertThat(r.status()).isEqualTo(Status.APPROX);
    assertThat(searched).isEmpty(); // 번호가 없어서 검색 API는 부르지 않아요
  }

  private static Found found(JusoResult... results) {
    return new Found(List.of(results), results.length);
  }

  private static JusoResult jusoAt(String admCd, String road, String main) {
    return new JusoResult(
        admCd, road, "0", main, "0", "269904000001", null, "부산광역시", "시험구", null, null, null);
  }

  private static JusoResult juso(String road, String underground, String main, String sub) {
    return new JusoResult(
        BJD, road, underground, main, sub, null, null, "부산광역시", "시험구", "시험동", null, null);
  }

  private static String id(String tag) {
    return ("26990" + tag + "0".repeat(26)).substring(0, 26);
  }

  private static void address(
      String road, int underground, int main, int sub, String tag, double lng, double lat)
      throws Exception {
    exec(
        "insert into area.address_points (address_id, load_scope, bjd_code, sigungu_code, road_code,"
            + " road_name, underground, bldg_main, bldg_sub, geom, data_date) values ('"
            + id(tag)
            + "', '99', '"
            + BJD
            + "', '26990', '26990"
            + tag
            + "', '"
            + road
            + "', "
            + underground
            + ", "
            + main
            + ", "
            + sub
            + ", st_makepoint("
            + lng
            + ", "
            + lat
            + ")::geography, date '2026-09-30')");
  }

  /** 시험구 시군구 경계: (lng, lat)에서 0.02도 정사각형. */
  private static void sigunguBoundary(double lng, double lat) throws Exception {
    exec(
        "insert into area.region_boundaries (level, code, name, geom, data_date) values ('SIG', '26990',"
            + " '시험구', 'SRID=4326;MULTIPOLYGON((("
            + lng
            + " "
            + lat
            + ", "
            + (lng + 0.02)
            + " "
            + lat
            + ", "
            + (lng + 0.02)
            + " "
            + (lat + 0.02)
            + ", "
            + lng
            + " "
            + (lat + 0.02)
            + ", "
            + lng
            + " "
            + lat
            + ")))'::geography, date '2026-09-30')");
  }
}
