package kr.mujuthaek.api.area.geocode;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class AddressNormalizerTest {

  @ParameterizedTest
  @CsvSource(
      delimiter = '|',
      textBlock =
          """
          서울특별시 강동구 길동 367-1 (5호선 길동역 1번 출구)      | 서울특별시 강동구 길동 367-1
          서울시 강남구 삼성동 140-32 (2호선 선릉역 10번 출구)       | 서울특별시 강남구 삼성동 140-32
          서울특별시 중구 광희동1가 166외 7필지 (동대문역 5번 출구)  | 서울특별시 중구 광희동1가 166
          서울특별시 종로구 숭인동 240-1 외 (동묘앞역 3번 출구)      | 서울특별시 종로구 숭인동 240-1
          인천광역시 부평구 부평동 65-17번지 일원                    | 인천광역시 부평구 부평동 65-17
          서울특별시 성동구 마장동 836일원 (왕십리역 6번 출구)       | 서울특별시 성동구 마장동 836
          서울특별시 관악구 남부순환로 180길 6 (신림역 1번 출구)     | 서울특별시 관악구 남부순환로180길 6
          칠곡군 왜관읍 달오 2길 76                                  | 칠곡군 왜관읍 달오2길 76
          광주광역시 광산구 첨단중앙로152번길 6-8                    | 전남광주통합특별시 광산구 첨단중앙로152번길 6-8
          광주시 오포읍 오포로 100                                   | 광주시 오포읍 오포로 100
          경상북도 김천시 용머리2길 15(감호동) , 예지하이츠          | 경상북도 김천시 용머리2길 15 예지하이츠
          """)
  void cleansUpNoticeAddresses(String raw, String expected) {
    assertThat(AddressNormalizer.normalize(raw).text()).isEqualTo(expected);
  }

  @ParameterizedTest
  @CsvSource(
      delimiter = '|',
      textBlock =
          """
          가장동 52-37(어반힐스3,청년임대) 대전광역시 서구 유등로465번길 61 (어반힐스3) | 대전광역시 서구 유등로465번길 61
          괴정동 3-18외(삼영빌딩,청년임대) 대전광역시 서구 계룡로 568 (삼영빌딩)         | 대전광역시 서구 계룡로 568
          """)
  void startsFromSidoWhenALotNumberIsWrittenFirst(String raw, String expected) {
    assertThat(AddressNormalizer.normalize(raw).text()).isEqualTo(expected);
  }

  @ParameterizedTest
  @CsvSource(
      delimiter = '|',
      textBlock =
          """
          전남광주통합특별시 여수시 미평로 77(미평동,미평주공아파트) | 미평동
          대구광역시 북구 노원로10길 40(노원동3가)                    | 노원동3가
          서울특별시 강서구 화곡로 146(5호선 화곡역 6번 출구)         |
          """)
  void keepsDongNameFoundInParentheses(String raw, String dong) {
    assertThat(AddressNormalizer.normalize(raw).dongHint()).isEqualTo(dong);
  }
}
