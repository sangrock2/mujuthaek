package kr.mujuthaek.api.area.geocode;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class JusoCandidatesTest {

  private static final JusoResult EXACT = result("1111010100", "평창문화로", "45", "0", "0");
  private static final JusoResult NEIGHBOR = result("1111010100", "평창문화로", "45", "1", "0");
  private static final ParsedAddress ADDRESS = AddressParser.parse("서울특별시종로구평창문화로45");

  @Test
  void compactAddressMatchesOnlyTheExactBuilding() {
    assertThat(ADDRESS.sigungu()).isEqualTo("종로구");
    assertThat(ADDRESS.roadName()).isEqualTo("평창문화로");
    assertThat(
            JusoCandidates.pick(
                new SearchOutcome.Found(List.of(NEIGHBOR, EXACT), 2), ADDRESS, null, "11110"))
        .contains(EXACT);
  }

  @Test
  void sameEntranceListedTwiceIsPicked() {
    assertThat(
            JusoCandidates.pick(
                new SearchOutcome.Found(List.of(EXACT, EXACT), 2), ADDRESS, "1111010100", "11110"))
        .contains(EXACT);
  }

  @Test
  void singleLookalikeIsNeverAccepted() {
    var wrong =
        List.of(
            NEIGHBOR,
            result("1111010100", "평창문화로1길", "45", "0", "0"),
            result("1111010100", "평창문화로", "45", "0", "1"),
            result("1168010100", "평창문화로", "45", "0", "0"));
    for (var candidate : wrong) {
      assertThat(
              JusoCandidates.pick(
                  new SearchOutcome.Found(List.of(candidate), 1), ADDRESS, null, "11110"))
          .isEmpty();
    }
  }

  @Test
  void incompleteResponseCannotEstablishUniqueness() {
    assertThat(
            JusoCandidates.pick(
                new SearchOutcome.Found(List.of(EXACT), 11), ADDRESS, null, "11110"))
        .isEmpty();
  }

  @Test
  void parcelMustMatchLotNumberAndMountainMarker() {
    var actual =
        new JusoResult(
            "1111010100",
            "평창문화로",
            "0",
            "45",
            "0",
            null,
            null,
            "서울특별시",
            "종로구",
            "평창동",
            "서울특별시 종로구 평창동 산 3-2",
            null);
    var found = new SearchOutcome.Found(List.of(actual), 1);
    assertThat(JusoCandidates.pick(found, AddressParser.parse("서울시 종로구 평창동 산 3-2"), null, "11110"))
        .contains(actual);
    assertThat(JusoCandidates.pick(found, AddressParser.parse("서울시 종로구 평창동 3-2"), null, "11110"))
        .isEmpty();
    assertThat(JusoCandidates.pick(found, AddressParser.parse("서울시 종로구 평창동 산 3"), null, "11110"))
        .isEmpty();
  }

  @Test
  void rejectsConflictingLegalDongAndMissingAddressParts() {
    var found = new SearchOutcome.Found(List.of(EXACT), 1);
    assertThat(JusoCandidates.pick(found, ADDRESS, "1111010200", "11110")).isEmpty();
    assertThat(JusoCandidates.pick(found, AddressParser.parse("서울 종로구 평창문화로"), null, null))
        .isEmpty();
  }

  @Test
  void comparesExplicitRegionNamesWhenNoRegionCodeWasResolved() {
    var found = new SearchOutcome.Found(List.of(EXACT), 1);
    assertThat(JusoCandidates.pick(found, ADDRESS, null, null)).contains(EXACT);
    assertThat(JusoCandidates.pick(found, AddressParser.parse("서울 강남구 평창문화로 45"), null, null))
        .isEmpty();
  }

  @Test
  void addressesWithoutADistrictCannotPickBetweenTwoExactEntrances() {
    var second = result("1168010100", "평창문화로", "45", "0", "0");
    assertThat(
            JusoCandidates.pick(
                new SearchOutcome.Found(List.of(EXACT, second), 2),
                AddressParser.parse("평창문화로 45"),
                null,
                null))
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

  private static JusoResult result(
      String admCd, String rn, String main, String sub, String underground) {
    return new JusoResult(
        admCd, rn, underground, main, sub, null, null, "서울특별시", "종로구", null, null, null);
  }
}
