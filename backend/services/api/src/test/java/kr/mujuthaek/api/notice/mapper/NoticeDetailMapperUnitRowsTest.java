package kr.mujuthaek.api.notice.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.UnitType;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * 공급 묶음별 주택형 줄(2026-10-26 원문 대조에서 나온 화면 변환 문제를 일반 규칙으로): 다른 묶음은 이름이 같아도 합치지 않고, 전체·대상별 수량을 두 번 세지
 * 않고, 가격 대상(가군·나군)마다 줄을 나누고, 분양가를 보여 줘요. 합성 자료예요.
 */
class NoticeDetailMapperUnitRowsTest {

  private static final JsonMapper JSON = JsonMapper.builder().build();

  private static JsonNode detail(String supplyGroups) {
    return JSON.readTree(
        """
        {"locations":[{"id":"a","complexName":"가상 A단지"},{"id":"b","complexName":"가상 B단지"}],
         "quality":{"heldItems":[]},
         "supplyGroups":%s}
        """
            .formatted(supplyGroups));
  }

  private static String count(int value, String... targets) {
    return """
        {"kind":"OFFERED","value":%d,"aggregationRole":"STANDALONE","parentCountId":null,
         "scope":{"targetGroups":%s}}"""
        .formatted(value, JSON.writeValueAsString(List.of(targets)));
  }

  private static String price(String kind, long won, String... targets) {
    return """
        {"kind":"%s","amountKrw":%d,"evidenceIds":[],"scope":{"targetGroups":%s}}"""
        .formatted(kind, won, JSON.writeValueAsString(List.of(targets)));
  }

  @Test
  void 묶음_전체_수량과_대상별_수량을_두_번_세지_않는다() {
    List<UnitType> rows =
        NoticeDetailMapper.unitTypes(
            detail(
                """
                [{"id":"g1","housingTypeCode":"059.9000A 59A","locationId":"a","exclusiveAreaSqm":59.9,
                  "scope":{"targetGroups":[]},"counts":[%s,%s,%s],"prices":[]}]
                """
                    .formatted(count(34), count(21, "사전청약"), count(13, "일반공급"))));
    assertThat(rows).singleElement().extracting(UnitType::supplyCount).isEqualTo(34);
    // 전체 수량이 없으면 대상별 수량의 합
    List<UnitType> byTarget =
        NoticeDetailMapper.unitTypes(
            detail(
                """
                [{"id":"g1","housingTypeCode":"26A","locationId":"a","exclusiveAreaSqm":26,
                  "scope":{"targetGroups":[]},"counts":[%s,%s],"prices":[]}]
                """
                    .formatted(count(5, "청년"), count(7, "신혼부부"))));
    assertThat(byTarget.getFirst().supplyCount()).isEqualTo(12);
  }

  @Test
  void 단지가_다른_묶음은_이름이_같아도_합치지_않는다() {
    List<UnitType> rows =
        NoticeDetailMapper.unitTypes(
            detail(
                """
                [{"id":"g1","housingTypeCode":"36A","locationId":"a","exclusiveAreaSqm":36,
                  "scope":{"targetGroups":["청년"]},"counts":[%s],"prices":[%s]},
                 {"id":"g2","housingTypeCode":"36A","locationId":"b","exclusiveAreaSqm":36,
                  "scope":{"targetGroups":["신혼부부"]},"counts":[%s],"prices":[%s]}]
                """
                    .formatted(
                        count(5),
                        price("DEPOSIT", 25_840_000),
                        count(12),
                        price("DEPOSIT", 71_957_000))));
    assertThat(rows)
        .extracting(UnitType::siteName, UnitType::supplyCount, UnitType::depositWon)
        .containsExactly(
            org.assertj.core.groups.Tuple.tuple("가상 A단지", 5, 25_840_000L),
            org.assertj.core.groups.Tuple.tuple("가상 B단지", 12, 71_957_000L));
  }

  @Test
  void 가격_대상마다_줄을_나누고_호수는_첫_줄에만_적는다() {
    List<UnitType> rows =
        NoticeDetailMapper.unitTypes(
            detail(
                """
                [{"id":"g1","housingTypeCode":"18","locationId":"a","exclusiveAreaSqm":18,
                  "scope":{"targetGroups":[]},"counts":[%s],
                  "prices":[%s,%s,%s,%s]}]
                """
                    .formatted(
                        count(20),
                        price("DEPOSIT", 1_407_000, "가군"),
                        price("MONTHLY_RENT", 27_000, "가군"),
                        price("DEPOSIT", 2_950_000, "나군"),
                        price("MONTHLY_RENT", 64_600, "나군"))));
    assertThat(rows)
        .extracting(
            UnitType::targetGroups, UnitType::depositWon, UnitType::rentWon, UnitType::supplyCount)
        .containsExactly(
            org.assertj.core.groups.Tuple.tuple(List.of("가군"), 1_407_000L, 27_000L, 20),
            org.assertj.core.groups.Tuple.tuple(List.of("나군"), 2_950_000L, 64_600L, null));
    assertThat(rows).extracting(UnitType::supplyGroupId).containsOnly("g1");
  }

  @Test
  void 가격만_있는_분양가_묶음은_같은_단지_같은_주택형의_수량_묶음에_붙는다() {
    List<UnitType> rows =
        NoticeDetailMapper.unitTypes(
            detail(
                """
                [{"id":"g1","housingTypeCode":"059.9000A 59A","locationId":"a","exclusiveAreaSqm":59.9,
                  "scope":{"targetGroups":[]},"counts":[%s],"prices":[]},
                 {"id":"p1","housingTypeCode":"059.0000A 59A","locationId":"a","exclusiveAreaSqm":59,
                  "scope":{"targetGroups":[]},"counts":[],"prices":[%s]},
                 {"id":"p2","housingTypeCode":"059.0000A 59A","locationId":"a","exclusiveAreaSqm":59,
                  "scope":{"targetGroups":[]},"counts":[],"prices":[%s]}]
                """
                    .formatted(
                        count(34),
                        price("SALE_PRICE", 386_430_000),
                        price("SALE_PRICE", 401_000_000))));
    assertThat(rows).singleElement();
    UnitType row = rows.getFirst();
    assertThat(row.houseType()).isEqualTo("059.9000A 59A");
    assertThat(row.exclusiveM2()).isEqualByComparingTo("59.9");
    assertThat(row.supplyCount()).isEqualTo(34);
    assertThat(row.salePriceMinWon()).isEqualTo(386_430_000L);
    assertThat(row.salePriceMaxWon()).isEqualTo(401_000_000L);
  }

  @Test
  void 대상별_합에서_소계_줄은_빼고_총_세대수보다_크면_비운다() {
    String housing =
        """
        {"kind":"TOTAL_HOUSING","value":25,"aggregationRole":"STANDALONE","parentCountId":null,"scope":{"targetGroups":[]}}""";
    List<UnitType> rows =
        NoticeDetailMapper.unitTypes(
            detail(
                """
                [{"id":"g1","housingTypeCode":"060.9495A","locationId":"a","exclusiveAreaSqm":60.9,
                  "scope":{"targetGroups":[]},"counts":[%s,%s,%s,%s,%s],"prices":[]}]
                """
                    .formatted(
                        housing,
                        count(2, "이주자 주택 대상자"),
                        count(21, "특별공급 계"),
                        count(2, "일반공급"),
                        count(20, "생애최초"))));
    // 이주자 2 + 일반 2 + 생애최초 20 = 24 (특별공급 계 21은 빼요)
    assertThat(rows.getFirst().supplyCount()).isEqualTo(24);
    List<UnitType> overlapping =
        NoticeDetailMapper.unitTypes(
            detail(
                """
                [{"id":"g1","housingTypeCode":"060.9495A","locationId":"a","exclusiveAreaSqm":60.9,
                  "scope":{"targetGroups":[]},"counts":[%s,%s,%s],"prices":[]}]
                """
                    .formatted(housing, count(20, "신혼부부"), count(20, "생애최초"))));
    assertThat(overlapping.getFirst().supplyCount()).isNull();
  }

  @Test
  void 묶음_합이_공고_모집_호수보다_크면_같은_코드_같은_호수의_병합_칸_복사를_비운다() {
    JsonNode detail =
        JSON.readTree(
            """
            {"locations":[{"id":"a","complexName":"가상 A단지"}],"quality":{"heldItems":[]},
             "notice":{"counts":[%s]},
             "supplyGroups":[
               {"id":"g1","housingTypeCode":"055.0000A 55A","locationId":"a","scope":{"targetGroups":[]},"counts":[%s],"prices":[]},
               {"id":"g2","housingTypeCode":"055.0000A 55AH","locationId":"a","scope":{"targetGroups":[]},"counts":[%s],"prices":[]},
               {"id":"g3","housingTypeCode":"055.0000B 55B","locationId":"a","scope":{"targetGroups":[]},"counts":[%s],"prices":[]}]}
            """
                .formatted(count(175, "신혼부부"), count(155), count(155), count(15)));
    assertThat(NoticeDetailMapper.unitTypes(detail))
        .extracting(UnitType::houseType, UnitType::supplyCount)
        .containsExactly(
            org.assertj.core.groups.Tuple.tuple("055.0000A 55A", null),
            org.assertj.core.groups.Tuple.tuple("055.0000A 55AH", null),
            org.assertj.core.groups.Tuple.tuple("055.0000B 55B", 15));
  }

  @Test
  void 하위_수량은_세지_않는다() {
    List<UnitType> rows =
        NoticeDetailMapper.unitTypes(
            detail(
                """
                [{"id":"g1","housingTypeCode":"44A","locationId":"a","exclusiveAreaSqm":44,
                  "scope":{"targetGroups":[]},
                  "counts":[{"id":"t","kind":"OFFERED","value":10,"aggregationRole":"TOTAL","parentCountId":null,"scope":{"targetGroups":[]}},
                            {"id":"c","kind":"OFFERED","value":4,"aggregationRole":"COMPONENT","parentCountId":"t","scope":{"targetGroups":[]}}],
                  "prices":[]}]
                """));
    assertThat(rows.getFirst().supplyCount()).isEqualTo(10);
  }
}
