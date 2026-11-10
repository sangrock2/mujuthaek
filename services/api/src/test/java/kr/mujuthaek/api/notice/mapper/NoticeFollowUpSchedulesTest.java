package kr.mujuthaek.api.notice.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/** 후속 안내에 저장하는 일정. 후속 안내는 일정만 저장하고 보류 항목은 두지 않아요. */
class NoticeFollowUpSchedulesTest {

  @Test
  void 보류한_일정은_후속_안내에_저장하지_않는다() {
    // 2026-11-10 코드 검토: 보류 표시 없이 일정만 저장해 보류한 일정이 확정처럼 보였음 (본 공고 상세는 보류한 일정을 뺌)
    ObjectNode envelope =
        (ObjectNode)
            NoticeContractTest.resource("/contracts/examples/extraction.completed.json").deepCopy();
    ObjectNode payload = (ObjectNode) envelope.path("payload");
    ObjectNode notice = (ObjectNode) payload.path("notice");
    ArrayNode schedules = (ArrayNode) notice.path("schedules");
    for (String kind : new String[] {"CONTRACT", "MOVE_IN"}) {
      ObjectNode copy = ((ObjectNode) schedules.get(0)).deepCopy();
      copy.put("id", kind.toLowerCase()).put("applicationMode", "NOT_APPLICABLE"); // 접수 일정이 아님
      copy.putArray("kinds").add(kind);
      schedules.add(copy);
    }
    ObjectNode quality = (ObjectNode) notice.path("quality");
    ArrayNode held = payload.putArray("heldItems");
    ArrayNode issues = quality.putArray("reviewIssues");
    for (String target : new String[] {"/schedules/1", "/schedules/2/endsAt"}) {
      ObjectNode item = held.addObject();
      item.put("target", target);
      item.put("extent", "ITEM");
      item.putArray("codes").add("API_MISMATCH");
      item.put("description", "확인이 필요합니다.");
      ObjectNode issue = issues.addObject();
      issue.put("code", "API_MISMATCH");
      issue.put("target", target);
      issue.put("description", "확인이 필요합니다.");
    }
    quality.set("heldItems", held.deepCopy());
    ((ObjectNode) quality.path("verification")).put("status", "PARTIALLY_PASSED");
    payload.put("reviewStatus", "PARTIALLY_PASSED");

    JsonNode saved = NoticeContent.schedules(ExtractionEvent.from(envelope));

    assertThat(saved).hasSize(1); // 일정 전체를 보류한 것도, 안의 칸 하나를 보류한 것도 빼요
    assertThat(saved.get(0).path("id").asString()).isEqualTo("application");
  }
}
