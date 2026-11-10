package kr.mujuthaek.api.area.repository;

import static kr.mujuthaek.api.area.AreaTestDatabase.exec;
import static org.assertj.core.api.Assertions.assertThat;

import kr.mujuthaek.api.area.AreaTestDatabase;
import kr.mujuthaek.api.area.domain.AddressMatch;
import kr.mujuthaek.api.area.domain.AddressMatch.Method;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/** 작은 사전 자료로 정확히·띄어쓰기·오타·없는 주소를 찾아봐요. 시험 시군구는 99로 시작해서 실제 자료와 섞이지 않아요. */
class PostgresAddressPointLookupTest {

  private final PostgresAddressPointLookup lookup =
      new PostgresAddressPointLookup(AreaTestDatabase.dataSource());

  @BeforeEach
  void dictionary() throws Exception {
    exec("delete from area.address_points where load_scope = '99'");
    exec("delete from area.road_names where sigungu_code like '99%'");
    address("99110", "초량상로", 0, 1, 2, "a1");
    address("99110", "초량상로", 1, 1, 2, "a2"); // 같은 번호의 지하
    address("99110", "중앙대로", 0, 10, 0, "a3");
    // 오타 하나가 두 도로명 모두에 가까운 경우
    address("99110", "해운대해변로", 0, 30, 0, "a4");
    address("99110", "해운대해변길", 0, 30, 0, "a5");
    // 같은 도로명·번호가 도로명코드만 달리 두 줄 (어느 것인지 모름)
    address("99110", "겹친로", 0, 5, 0, "a6");
    address("99110", "겹친로", 0, 5, 0, "a7");
    // 번호가 들어간 길: 10번지는 본오로7길에만 있어요
    address("99110", "본오로7길", 0, 10, 0, "a8");
    address("99110", "본오로9길", 0, 3, 0, "a9");
    address("99110", "본오로길", 0, 10, 0, "c1");
    // 섬 주소: 원천 지하 여부 코드 3 (검색 API는 0·1만 줘요)
    address("99110", "산양일주로", 3, 700, 0, "c2");
    address("99170", "초량상로", 0, 1, 2, "b1"); // 다른 시군구의 같은 이름
    exec(
        "insert into area.road_names select distinct sigungu_code, road_name from area.address_points"
            + " where load_scope = '99'");
  }

  @Test
  void findsExactlyAndIgnoresSpaces() {
    AddressMatch exact = lookup.find("99110", "초량상로", 0, 1, 2).orElseThrow();
    assertThat(exact.addressId()).isEqualTo(id("a1"));
    assertThat(exact.method()).isEqualTo(Method.FILE);
    assertThat(exact.bjdCode()).isEqualTo("9911010100");
    assertThat(exact.lat()).isEqualTo(35.1);
    assertThat(exact.lng()).isEqualTo(129.04);

    assertThat(lookup.find("99110", "초량 상로", 0, 1, 2))
        .map(AddressMatch::addressId)
        .contains(id("a1")); // 띄어쓰기는 지우고 정확히
    assertThat(lookup.find("99110", "초량상로", 1, 1, 2))
        .map(AddressMatch::addressId)
        .contains(id("a2")); // 지하는 따로
  }

  @Test
  void fixesATypoWithASimilarRoadName() {
    AddressMatch fixed = lookup.find("99110", "초량상노", 0, 1, 2).orElseThrow();
    assertThat(fixed.addressId()).isEqualTo(id("a1"));
    assertThat(fixed.roadName()).isEqualTo("초량상로");
    assertThat(fixed.method()).isEqualTo(Method.FUZZY);
  }

  @Test
  void findsNothingRatherThanGuessing() throws Exception {
    assertThat(lookup.find("99110", "초량상로", 0, 999, 0)).isEmpty(); // 없는 번호
    assertThat(lookup.find("99110", "전혀다른길", 0, 1, 2)).isEmpty(); // 비슷한 이름도 없음
    assertThat(lookup.find("99140", "초량상로", 0, 1, 2)).isEmpty(); // 다른 시군구에는 없음
    // 오타 후보 둘 다 맞음: 두 도로명 모두 유사도 기준을 넘어 후보가 되고, 둘 다 30번지가 있어서 고르지 않아요
    assertThat(
            AreaTestDatabase.one(
                "select count(*) from area.road_names where sigungu_code = '99110'"
                    + " and road_name % '해운대해변료'"))
        .isEqualTo("2");
    assertThat(lookup.find("99110", "해운대해변료", 0, 30, 0)).isEmpty();
    assertThat(lookup.find("99110", "겹친로", 0, 5, 0)).isEmpty(); // 같은 조건 주소가 둘
    assertThat(lookup.find("99110", "  ", 0, 1, 2)).isEmpty();
    assertThat(lookup.find(null, "초량상로", 0, 1, 2)).isEmpty();
  }

  @Test
  void numberedRoadsAreFixedOnlyForALetterTypo() {
    // 글자 오타는 고쳐요
    assertThat(lookup.find("99110", "본오노7길", 0, 10, 0))
        .map(AddressMatch::addressId)
        .contains(id("a8"));
    // 번호가 다르면 다른 길이라 고치지 않아요 (10번지가 있는 본오로7길로 가면 틀린 좌표)
    assertThat(lookup.find("99110", "본오로8길", 0, 10, 0)).isEmpty();
    // 번호가 깨져 사라진 이름도 고치지 않아요 (번호 없는 본오로길에도 10번지가 있어서 그리로 가면 틀린 좌표)
    assertThat(lookup.find("99110", "본오로가길", 0, 10, 0)).isEmpty();
  }

  @Test
  void findsAnyLevelOnlyWhenOneAddressRemains() {
    assertThat(lookup.find("99110", "산양일주로", 0, 700, 0)).isEmpty(); // 0으로는 못 찾음
    AddressMatch island = lookup.findAnyLevel("99110", "산양 일주로", 700, 0).orElseThrow();
    assertThat(island.addressId()).isEqualTo(id("c2"));
    assertThat(island.underground()).isEqualTo(3);
    // 지상(a1)·지하(a2)가 둘 다 있는 번지는 지하 여부를 빼면 둘이라 고르지 않아요
    assertThat(lookup.findAnyLevel("99110", "초량상로", 1, 2)).isEmpty();
    assertThat(lookup.findAnyLevel("99110", "초량상노", 1, 2)).isEmpty(); // 오타는 고치지 않음 (정확히만)
    assertThat(lookup.findAnyLevel(null, "산양일주로", 700, 0)).isEmpty();
  }

  @Test
  void oneLetterApartMeansSameLengthAndOneNonDigitLetter() {
    assertThat(PostgresAddressPointLookup.oneLetterApart("초량상노", "초량상로")).isTrue();
    assertThat(PostgresAddressPointLookup.oneLetterApart("초량상로", "초량상로")).isFalse();
    assertThat(PostgresAddressPointLookup.oneLetterApart("본오로8길", "본오로7길")).isFalse();
    assertThat(PostgresAddressPointLookup.oneLetterApart("본오로가길", "본오로7길")).isFalse();
    assertThat(PostgresAddressPointLookup.oneLetterApart("노원로1가길", "노원로1길")).isFalse();
    assertThat(PostgresAddressPointLookup.oneLetterApart("초랑상노", "초량상로")).isFalse();
  }

  @Test
  void otherSigunguWithTheSameNameIsSeparate() {
    assertThat(lookup.find("99170", "초량상로", 0, 1, 2))
        .map(AddressMatch::addressId)
        .contains(id("b1"));
  }

  /** 시험 주소 ID 26자리 (뒤에 표시 글자를 붙여 구분). */
  private static String id(String tag) {
    return ("99" + tag + "0".repeat(26)).substring(0, 26);
  }

  private static void address(
      String sigungu, String road, int underground, int main, int sub, String tag)
      throws Exception {
    exec(
        "insert into area.address_points (address_id, load_scope, bjd_code, sigungu_code, road_code,"
            + " road_name, underground, bldg_main, bldg_sub, geom, data_date) values ('"
            + id(tag)
            + "', '99', '"
            + sigungu
            + "10100', '"
            + sigungu
            + "', '"
            + sigungu
            + tag
            + "', '"
            + road
            + "', "
            + underground
            + ", "
            + main
            + ", "
            + sub
            + ", st_makepoint(129.04, 35.1)::geography, date '2026-09-30')");
  }
}
