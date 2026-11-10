package kr.mujuthaek.api.area.geocode;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import kr.mujuthaek.api.area.geocode.JusoCandidates.Hint;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class JusoCandidatesTest {

  // 초량상로 1-2는 부산 중구 영주동 (검색 API·주소 사전·경계 모두 26110)
  private static final JusoResult BUSAN = result("2611010100", "초량상로", "1", "2");
  private static final JusoResult BUSAN_OTHER_DONG = result("2611010300", "초량상로", "5", "0");
  // 실제 검색 API가 구를 잘못 쓴 "부산광역시 동구 초량상로 1-2"에 준 결과 2개: 동구의 비슷한 도로명뿐, 진짜 주소는 없음
  private static final JusoResult DONGGU_LOOKALIKE_35 = result("2617010100", "초량상로35번길", "1", "2");
  private static final JusoResult DONGGU_LOOKALIKE_105 =
      result("2617010100", "초량상로105번길", "1", "2");
  private static final JusoResult SEOUL = result("1168010100", "테헤란로", "152", "0");

  @Test
  void singleResultIsPicked() {
    assertThat(JusoCandidates.pick(List.of(SEOUL), Hint.none())).contains(SEOUL);
  }

  @Test
  void sameEntranceListedTwiceIsPicked() {
    JusoResult sameBuilding = result("2611010100", "초량상로", "1", "2");
    assertThat(JusoCandidates.pick(List.of(BUSAN, sameBuilding), Hint.none())).contains(BUSAN);
  }

  @Test
  void onlyLookalikeRoadsAreNotPicked() {
    // 실제 응답 그대로: 도로명이 똑같은 결과가 없고 번호·시군구도 둘이 같아서 고르지 않음
    assertThat(
            JusoCandidates.pick(
                List.of(DONGGU_LOOKALIKE_35, DONGGU_LOOKALIKE_105),
                new Hint(null, "26170", "초량상로", 1, 2)))
        .isEmpty();
  }

  @Test
  void exactRoadNameWinsOverLookalikesEvenWithWrongDistrict() {
    // 공고가 구를 잘못 적어도 도로명·번호가 똑같은 결과를 고름. 시군구가 맞는지는 경계 검사가 봐요
    assertThat(
            JusoCandidates.pick(
                List.of(DONGGU_LOOKALIKE_35, BUSAN), new Hint(null, "26170", "초량 상로", 1, 2)))
        .contains(BUSAN);
  }

  @Test
  void buildingNumberNarrowsSameRoad() {
    assertThat(
            JusoCandidates.pick(
                List.of(BUSAN, BUSAN_OTHER_DONG), new Hint(null, null, "초량상로", 5, null)))
        .contains(BUSAN_OTHER_DONG);
  }

  @Test
  void legalDongCodePicksOne() {
    assertThat(
            JusoCandidates.pick(
                List.of(BUSAN, BUSAN_OTHER_DONG, SEOUL),
                new Hint("2611010300", null, null, null, null)))
        .contains(BUSAN_OTHER_DONG);
  }

  @Test
  void sigunguPicksOneWhenDongDoesNotMatch() {
    assertThat(
            JusoCandidates.pick(
                List.of(BUSAN, SEOUL), new Hint("2611099999", "11680", null, null, null)))
        .contains(SEOUL);
  }

  @Test
  void ambiguousIsNotPicked() {
    assertThat(
            JusoCandidates.pick(
                List.of(BUSAN, BUSAN_OTHER_DONG), new Hint(null, "26110", null, null, null)))
        .isEmpty();
    assertThat(JusoCandidates.pick(List.of(BUSAN, SEOUL), Hint.none())).isEmpty();
    assertThat(JusoCandidates.pick(List.of(), new Hint("2611010100", "26110", null, null, null)))
        .isEmpty();
  }

  @ParameterizedTest
  @CsvSource(
      delimiter = '|',
      value = {
        "부산광역시 중구 초량상로 1-2|부산광역시 중구 초량상로 1-2",
        "초량상로 1-2 <A동>|초량상로 1-2 A동",
        "100%=분양 [특별]|100 분양 특별",
        "select * from 동|* from 동",
        "LOTTE TOWER 300|LOTTE TOWER 300",
        "  테헤란로   152  |테헤란로 152",
        "Union|''"
      })
  void keywordDropsCharactersTheApiRefuses(String raw, String cleaned) {
    assertThat(JusoKeyword.clean(raw)).isEqualTo(cleaned);
  }

  private static JusoResult result(String admCd, String rn, String main, String sub) {
    return new JusoResult(admCd, rn, "0", main, sub, null, null, null, null, null, null, null);
  }
}
