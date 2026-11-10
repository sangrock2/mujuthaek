package kr.mujuthaek.api.area.geocode;

import static org.assertj.core.api.Assertions.assertThat;

import kr.mujuthaek.api.area.geocode.ParsedAddress.Kind;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class AddressParserTest {

  @ParameterizedTest
  @CsvSource(
      delimiter = '|',
      textBlock =
          """
          경기도 화성시 효행구 봉담읍 동화북길43번길 5 금성타운       | 경기도         | 화성시 효행구 | 동화북길43번길      | 5   | 0
          경기도 화성시 만세구 향남읍 상신하길로175번나길 4-3        | 경기도         | 화성시 만세구 | 상신하길로175번나길 | 4   | 3
          강원특별자치도 춘천시 봉의산길22번길 24(옥천동)            | 강원특별자치도 | 춘천시        | 봉의산길22번길      | 24  | 0
          대구광역시 북구 칠곡중앙대로105길 11-1(읍내동) 하늘정원     | 대구광역시     | 북구          | 칠곡중앙대로105길    | 11  | 1
          경상북도 포항시 남구 문예로82번길 20-8(대도동) 302동        | 경상북도       | 포항시 남구   | 문예로82번길        | 20  | 8
          영주시 대동로34번길 23-3                                   |                | 영주시        | 대동로34번길        | 23  | 3
          """)
  void readsRoadNameAndBuildingNumber(
      String raw, String sido, String sigungu, String road, int main, int sub) {
    ParsedAddress parsed = AddressParser.parse(raw);

    assertThat(parsed.kind()).isEqualTo(Kind.ROAD);
    assertThat(parsed.sido()).isEqualTo(sido);
    assertThat(parsed.sigungu()).isEqualTo(sigungu);
    assertThat(parsed.roadName()).isEqualTo(road);
    assertThat(parsed.buildingMain()).isEqualTo(main);
    assertThat(parsed.buildingSub()).isEqualTo(sub);
  }

  @Test
  void buildingNameContainingJihaIsNotUnderground() {
    ParsedAddress parsed = AddressParser.parse("경상북도 김천시 용머리2길 15(감호동) , 예지하이츠");

    assertThat(parsed.underground()).isFalse();
    assertThat(parsed.dong()).isEqualTo("감호동");
  }

  @Test
  void undergroundBuildingNumber() {
    ParsedAddress parsed = AddressParser.parse("서울특별시 중구 세종대로 지하 2");

    assertThat(parsed.kind()).isEqualTo(Kind.ROAD);
    assertThat(parsed.underground()).isTrue();
    assertThat(parsed.buildingMain()).isEqualTo(2);
  }

  @ParameterizedTest
  @CsvSource(
      delimiter = '|',
      textBlock =
          """
          서울특별시 중구 광희동1가 166외 7필지 (동대문역 5번 출구) | 광희동1가     | false | 166  | 0
          전북특별자치도 익산시 낭산면 용기리 1953-1               | 낭산면 용기리 | false | 1953 | 1
          서울특별시 종로구 종로1가 12                             | 종로1가       | false | 12   | 0
          서울특별시 강동구 길동 367-1 (5호선 길동역 1번 출구)      | 길동          | false | 367  | 1
          강원특별자치도 춘천시 동산면 원창리 산 12-3              | 동산면 원창리 | true  | 12   | 3
          """)
  void readsLotNumberWhenThereIsNoRoadName(
      String raw, String dong, boolean mountain, int main, int sub) {
    ParsedAddress parsed = AddressParser.parse(raw);

    assertThat(parsed.kind()).isEqualTo(Kind.JIBUN);
    assertThat(parsed.dong()).isEqualTo(dong);
    assertThat(parsed.mountain()).isEqualTo(mountain);
    assertThat(parsed.jibunMain()).isEqualTo(main);
    assertThat(parsed.jibunSub()).isEqualTo(sub);
  }

  @Test
  void prefersRoadNameWhenBothAreWritten() {
    ParsedAddress parsed =
        AddressParser.parse("가장동 52-37(어반힐스3,청년임대) 대전광역시 서구 유등로465번길 61 (어반힐스3)");

    assertThat(parsed.kind()).isEqualTo(Kind.ROAD);
    assertThat(parsed.sigungu()).isEqualTo("서구");
    assertThat(parsed.roadName()).isEqualTo("유등로465번길");
  }

  @Test
  void areaWithoutNumbersIsAreaOnly() {
    assertThat(AddressParser.parse("인천광역시 계양구 박촌동 인천계양 테크노밸리 공공주택지구 내 A17블록").kind())
        .isEqualTo(Kind.AREA_ONLY);
    assertThat(AddressParser.parse("서울특별시 강남구 일대").kind()).isEqualTo(Kind.AREA_ONLY);
    assertThat(AddressParser.parse("추후 공고").kind()).isEqualTo(Kind.UNKNOWN);
    assertThat(AddressParser.parse(null).kind()).isEqualTo(Kind.UNKNOWN);
  }
}
