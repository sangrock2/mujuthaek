package kr.mujuthaek.api.notice.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.JsonNodeFactory;
import tools.jackson.databind.node.ObjectNode;

/** 정정 결과가 지금 공개된 버전의 핵심 섹션(공급·자격·위치)을 비우는지. 비우면 공고를 통째로 바꾸지 않고 후속 안내로 붙여요. */
class NoticeCorrectionSectionsTest {

  private static ObjectNode detail() {
    return (ObjectNode)
        NoticeContractTest.resource("/contracts/examples/extraction.completed.json")
            .path("payload")
            .path("notice")
            .deepCopy();
  }

  private static ArrayNode held(String... targets) {
    ArrayNode items = JsonNodeFactory.instance.arrayNode();
    for (String target : targets) {
      items.addObject().put("target", target);
    }
    return items;
  }

  @Test
  void aShortCorrectionThatLeavesCoreSectionsEmptyOrHeldIsDetected() {
    // 2026-11-10 재검토: 「당첨자 발표일 변경」 같은 짧은 정정의 결과가 원공고 전체를 바꿔 공급·자격·위치가 사라졌음
    JsonNode previous = detail();

    assertThat(NoticeContent.droppedCoreSections(previous, held(), detail(), held()))
        .isEmpty(); // 공고문 전체를 고친 정정은 그대로 새 버전

    ObjectNode emptied = detail();
    emptied.putArray("supplyGroups");
    emptied.putArray("locations");
    assertThat(NoticeContent.droppedCoreSections(previous, held(), emptied, held()))
        .containsExactly("supplyGroups", "locations");

    assertThat(NoticeContent.droppedCoreSections(previous, held(), detail(), held("/eligibility")))
        .containsExactly("eligibility"); // 섹션 전체를 보류한 것도 쓸 항목이 없음
    assertThat(
            NoticeContent.droppedCoreSections(
                previous, held(), detail(), held("/eligibility/0/rule")))
        .isEmpty(); // 칸 하나만 보류한 항목은 쓸 항목
    assertThat(NoticeContent.droppedCoreSections(previous, held("/locations"), emptied, held()))
        .containsExactly("supplyGroups"); // 지금 버전에서도 보류였던 섹션은 견주지 않음
  }
}
