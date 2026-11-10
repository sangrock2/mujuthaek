package kr.mujuthaek.api.notice.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import java.util.function.Consumer;
import kr.mujuthaek.api.notice.NoticeFixtures;
import kr.mujuthaek.api.notice.domain.NoticeType;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.Guidance;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.SelectionRule;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.node.ObjectNode;

/** 상세의 선정 방식·안내 (프론트 요청 2026-10-26)와 공공임대 공고 유형. */
class NoticeDetailMapperGuidanceTest {

  private static NoticeDetailResponse map(Consumer<ObjectNode> change) {
    ObjectNode p = NoticeFixtures.payload(UUID.randomUUID(), 1);
    change.accept((ObjectNode) p.get("notice"));
    return NoticeDetailMapper.map(
        null,
        p,
        List.of(),
        List.of(),
        1,
        false,
        OffsetDateTime.parse("2026-10-22T09:00:00+09:00"),
        LocalDate.of(2026, 10, 22));
  }

  @Test
  void 선정_방식과_안내를_원문_순서로_보여준다() {
    NoticeDetailResponse detail =
        map(
            n -> {
              ObjectNode contact = ((ObjectNode) n.get("guidance").get(0)).deepCopy();
              contact
                  .put("id", "contact")
                  .put("kind", "CONTACT")
                  .put("title", "콜센터")
                  .put("phone", "1600-0000")
                  .putNull("url");
              n.withArray("guidance").add(contact);
            });

    assertThat(detail.selectionRules())
        .extracting(SelectionRule::id, SelectionRule::kind, SelectionRule::priorityRank)
        .containsExactly(
            org.assertj.core.groups.Tuple.tuple("priority", "PRIORITY", 1),
            org.assertj.core.groups.Tuple.tuple("children-score", "SCORING", null));
    assertThat(detail.selectionRules().get(1).points()).isEqualByComparingTo("2");
    assertThat(detail.selectionRules().get(0).evidence()).hasSize(1);
    assertThat(detail.guidance())
        .extracting(Guidance::kind, Guidance::title, Guidance::phone)
        .containsExactly(
            org.assertj.core.groups.Tuple.tuple("APPLICATION_METHOD", "온라인 신청", null),
            org.assertj.core.groups.Tuple.tuple("CONTACT", "콜센터", "1600-0000"));
    assertThat(detail.guidance().get(0).url()).isEqualTo("https://example.org/apply");
  }

  @Test
  void 보류한_선정_방식과_안내는_빼요() {
    NoticeDetailResponse detail =
        map(
            n -> {
              var held = n.withObject("quality").withArray("heldItems");
              held.addObject().put("target", "/selectionRules/0").put("description", "확인 중");
              held.addObject().put("target", "/guidance").put("description", "확인 중");
            });

    assertThat(detail.selectionRules())
        .extracting(SelectionRule::id)
        .containsExactly("children-score");
    assertThat(detail.guidance()).isEmpty();
  }

  @Test
  void 공공임대는_통합공공임대_공공지원민간임대와_구분한다() {
    assertThat(NoticeType.fromSupplyType("10년 공공임대", "HOUSING"))
        .isEqualTo(NoticeType.PUBLIC_RENTAL);
    assertThat(NoticeType.fromSupplyType("10년·분양전환", "HOUSING"))
        .isEqualTo(NoticeType.PUBLIC_RENTAL);
    assertThat(NoticeType.fromSupplyType("분납임대", "HOUSING")).isEqualTo(NoticeType.PUBLIC_RENTAL);
    assertThat(NoticeType.fromSupplyType("통합공공임대", "HOUSING"))
        .isEqualTo(NoticeType.INTEGRATED_PUBLIC_RENTAL);
    assertThat(NoticeType.fromSupplyType("공공지원 민간임대", "HOUSING"))
        .isEqualTo(NoticeType.PUBLIC_SUPPORT_PRIVATE_RENTAL);
  }
}
