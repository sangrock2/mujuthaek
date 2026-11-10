package kr.mujuthaek.api.notice.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.notice.NoticeFixtures;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/** 원문 확인 전까지 보류한 항목은 상세에 보여 주지 않고, 무엇을 뺐는지 알려요. */
class NoticeDetailMapperHeldTest {

  private static final LocalDate TODAY = LocalDate.of(2026, 10, 22);

  private static NoticeDetailResponse map(String... targets) {
    ObjectNode p = NoticeFixtures.payload(UUID.randomUUID(), 1);
    ArrayNode held = ((ObjectNode) p.get("notice").get("quality")).putArray("heldItems");
    for (String target : targets) {
      held.addObject().put("target", target).put("description", "원문 확인 필요: " + target);
    }
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

  @Test
  void 보류가_없으면_모두_보여준다() {
    NoticeDetailResponse detail = map();

    assertThat(detail.schedules()).hasSize(1);
    assertThat(detail.unitTypes()).hasSize(1);
    assertThat(detail.sites()).singleElement().satisfies(s -> assertThat(s.address()).isNotNull());
    assertThat(detail.summary().supplyTotal()).isEqualTo(1);
    assertThat(detail.heldItems()).isEmpty();
  }

  @Test
  void 보류한_일정_공급_묶음_첨부는_빼고_무엇을_뺐는지_알려준다() {
    NoticeDetailResponse detail = map("/schedules/0", "/supplyGroups/0", "/documents/0");

    assertThat(detail.schedules()).isEmpty();
    assertThat(detail.unitTypes()).isEmpty(); // 공급 묶음 전체를 보류하면 그 주택형은 빼요
    assertThat(detail.files()).isEmpty();
    assertThat(detail.heldItems())
        .extracting(NoticeDetailResponse.HeldItem::section)
        .containsExactly("schedules", "supplyGroups", "documents");
  }

  @Test
  void 위치는_보류한_칸만_비우고_위치_전체를_보류하면_뺀다() {
    assertThat(map("/locations/0/address").sites())
        .singleElement()
        .satisfies(
            s -> {
              assertThat(s.address()).isNull();
              assertThat(s.name()).isNotNull();
              assertThat(s.regionCode()).isEqualTo("11110");
            });
    assertThat(map("/locations/0").sites()).isEmpty();
    assertThat(NoticeDetailMapper.units(heldDetail("/locations/0/address"), null))
        .singleElement()
        .satisfies(u -> assertThat(u.address()).isNull());
  }

  @Test
  void 보류한_공급_수와_자격_조건은_쓰지_않거나_확인_필요로_표시한다() {
    NoticeDetailResponse detail = map("/notice/counts", "/eligibility/1");

    assertThat(detail.summary().supplyTotal()).isNull();
    assertThat(detail.conditions())
        .extracting(NoticeDetailResponse.Condition::inReview)
        .containsExactly(false, true, false);
  }

  @Test
  void 보류한_호는_주택목록에서_뺀다() {
    assertThat(NoticeDetailMapper.units(heldDetail("/supplyGroups/0"), null)).isEmpty();
  }

  private static ObjectNode heldDetail(String target) {
    ObjectNode detail = (ObjectNode) NoticeFixtures.payload(UUID.randomUUID(), 1).get("notice");
    ((ObjectNode) detail.get("quality")).putArray("heldItems").addObject().put("target", target);
    return detail;
  }
}
