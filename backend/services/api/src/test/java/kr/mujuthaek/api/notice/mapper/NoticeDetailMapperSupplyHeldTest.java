package kr.mujuthaek.api.notice.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.notice.NoticeFixtures;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.UnitType;
import kr.mujuthaek.api.notice.dto.response.NoticeUnitResponse;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/**
 * 공급 묶음의 보류 범위에 따라 가리는 값: 묶음 전체(또는 수량·가격 밖의 칸)를 보류하면 그 주택형·호를 빼고, 수량만 보류하면 공급 호수만, 가격만 보류하면 그 가격만
 * 비워요.
 *
 * <p>공급 묶음: 0번은 예시의 호(20A, 보증금 100만·월임대료 10만, 근거 e1), 1번은 이 시험에서 넣는 주택형 묶음(30B, 모집 5호, 보증금
 * 200만·월임대료 20만).
 */
class NoticeDetailMapperSupplyHeldTest {

  private static final LocalDate TODAY = LocalDate.of(2026, 10, 22);

  @Test
  void 수량만_보류하면_주택형은_보여주고_공급_호수와_주택형별_합만_비운다() {
    for (String target : List.of("/supplyGroups/1/counts", "/supplyGroups/1/counts/0/value")) {
      NoticeDetailResponse detail = map(target);

      assertThat(detail.unitTypes()).extracting(UnitType::houseType).containsExactly("20A", "30B");
      UnitType b = type(detail, "30B");
      assertThat(b.supplyCount()).as(target).isNull();
      assertThat(b.depositWon()).isEqualTo(2_000_000L);
      assertThat(b.rentWon()).isEqualTo(200_000L);
      assertThat(b.exclusiveM2()).isEqualByComparingTo("30");
      assertThat(type(detail, "20A").supplyCount()).isEqualTo(1);
      // 수량을 모르는 묶음이 있어 주택형별 합을 공고 모집 수로 쓰지 않아요
      assertThat(detail.summary().supplyTotal()).as(target).isNull();
      assertThat(detail.heldItems())
          .extracting(NoticeDetailResponse.HeldItem::target)
          .containsExactly(target);
    }
  }

  @Test
  void 가격만_보류하면_그_묶음의_보증금_월임대료와_근거만_비운다() {
    NoticeDetailResponse detail = map("/supplyGroups/0/prices");

    UnitType a = type(detail, "20A");
    assertThat(a.depositWon()).isNull();
    assertThat(a.rentWon()).isNull();
    assertThat(a.evidence()).isEmpty();
    assertThat(a.supplyCount()).isEqualTo(1);
    assertThat(a.exclusiveM2()).isEqualByComparingTo("20");
    assertThat(type(detail, "30B").depositWon()).isEqualTo(2_000_000L);
    // 수량은 확정이라 주택형별 합을 써요
    assertThat(detail.summary().supplyTotal()).isEqualTo(6);

    assertThat(NoticeDetailMapper.units(detail("/supplyGroups/0/prices"), null))
        .singleElement()
        .satisfies(
            u -> {
              assertThat(u.unitLabel()).isNotNull();
              assertThat(u.depositWon()).isNull();
              assertThat(u.rentWon()).isNull();
              assertThat(u.evidence()).isEmpty();
            });
  }

  @Test
  void 가격_항목_하나만_보류하면_그_종류만_비운다() {
    // 1번 가격(월임대료)의 금액만 보류: 보증금은 보여 줘요
    String rentAmount = "/supplyGroups/0/prices/1/amountKrw";
    UnitType a = type(map(rentAmount), "20A");
    assertThat(a.depositWon()).isEqualTo(1_000_000L);
    assertThat(a.rentWon()).isNull();
    assertThat(a.evidence()).isNotEmpty(); // 보증금의 근거
    NoticeUnitResponse unit = NoticeDetailMapper.units(detail(rentAmount), null).getFirst();
    assertThat(unit.depositWon()).isEqualTo(1_000_000L);
    assertThat(unit.rentWon()).isNull();

    // 첫 가격 항목(보증금) 전체를 보류하면 그 항목의 종류도 몰라, 그 뒤의 월임대료까지 보증금·월임대료 모두 비워요
    UnitType whole = type(map("/supplyGroups/0/prices/0"), "20A");
    assertThat(whole.depositWon()).isNull();
    assertThat(whole.rentWon()).isNull();
    assertThat(whole.supplyCount()).isEqualTo(1);
  }

  @Test
  void 묶음_전체나_수량_가격_밖의_칸을_보류하면_그_주택형을_뺀다() {
    for (String target :
        List.of("/supplyGroups/1", "/supplyGroups/1/exclusiveAreaSqm", "/supplyGroups")) {
      NoticeDetailResponse detail = map(target);

      assertThat(detail.unitTypes())
          .as(target)
          .extracting(UnitType::houseType)
          .doesNotContain("30B");
      assertThat(detail.summary().supplyTotal()).as(target).isNull();
    }
    assertThat(NoticeDetailMapper.units(detail("/supplyGroups/0/floor"), null)).isEmpty();
  }

  @Test
  void 보류가_없으면_주택형별_합을_모집_수로_쓴다() {
    NoticeDetailResponse detail = map();

    assertThat(detail.unitTypes()).hasSize(2);
    assertThat(detail.summary().supplyTotal()).isEqualTo(6);
  }

  private static UnitType type(NoticeDetailResponse detail, String houseType) {
    return detail.unitTypes().stream()
        .filter(t -> t.houseType().equals(houseType))
        .findFirst()
        .orElseThrow();
  }

  private static NoticeDetailResponse map(String... targets) {
    ObjectNode p = payload(targets);
    return NoticeDetailMapper.map(
        null,
        p,
        List.of(),
        List.of(),
        1,
        false,
        OffsetDateTime.parse("2026-10-22T09:00:00+09:00"),
        TODAY);
  }

  private static ObjectNode detail(String... targets) {
    return (ObjectNode) payload(targets).get("notice");
  }

  /** 예시 공고에 주택형 묶음(30B)을 하나 더 넣고 보류 항목을 붙여요. 공고에 적힌 모집 수는 지워 주택형별 합을 쓰게 해요. */
  private static ObjectNode payload(String... targets) {
    ObjectNode p = NoticeFixtures.payload(UUID.randomUUID(), 1);
    ObjectNode notice = (ObjectNode) p.get("notice");
    ((ObjectNode) notice.get("notice")).putArray("counts");
    ObjectNode group = ((ArrayNode) notice.get("supplyGroups")).addObject();
    group.put("id", "type-30b");
    group.put("locationId", "building-a");
    group.put("housingTypeCode", "30B");
    group.put("itemKind", "HOUSING_TYPE");
    group.put("exclusiveAreaSqm", 30);
    group.putArray("counts").addObject().put("kind", "OFFERED").put("value", 5);
    ArrayNode prices = group.putArray("prices");
    prices.addObject().put("kind", "DEPOSIT").put("amountKrw", 2_000_000);
    prices.addObject().put("kind", "MONTHLY_RENT").put("amountKrw", 200_000);
    ArrayNode held = ((ObjectNode) notice.get("quality")).putArray("heldItems");
    for (String target : targets) {
      held.addObject().put("target", target).put("description", "원문 확인 필요: " + target);
    }
    return p;
  }
}
