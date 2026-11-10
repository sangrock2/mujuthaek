package kr.mujuthaek.api.notice.controller;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.UUID;
import kr.mujuthaek.api.notice.NoticeApiFixture;
import kr.mujuthaek.api.notice.NoticeFixtures;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.node.ObjectNode;

class NoticeVersionsApiTest {

  private final NoticeApiFixture f = new NoticeApiFixture();
  private final MockMvc mvc = f.mvc(new NoticeController(f.queries));

  @Test
  void correctionsShowWhatChanged() throws Exception {
    UUID id = f.notice(p -> {});
    UUID original =
        f.jdbc.queryForObject(
            "select raw_post_id from notice.notices where id = ?", UUID.class, id);
    ObjectNode fix = NoticeFixtures.correction(UUID.randomUUID(), original);
    fix.put("provider", f.provider);
    NoticeFixtures.schedule(fix, "2026-10-01", "2026-11-07");
    fix.put("summary", "마감일을 늦췄어요");
    f.receive(fix);
    ObjectNode inReview = NoticeFixtures.correction(UUID.randomUUID(), original);
    inReview.put("reviewStatus", "IN_REVIEW"); // 공개되지 않은 버전은 이력에 없어요
    f.receive(inReview);

    mvc.perform(get("/api/v1/notices/{id}/versions", id))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.length()").value(2))
        .andExpect(jsonPath("$[0].version").value(1))
        .andExpect(jsonPath("$[0].kind").value("NOTICE"))
        .andExpect(jsonPath("$[0].changedFields.length()").value(0))
        .andExpect(jsonPath("$[1].version").value(2))
        .andExpect(jsonPath("$[1].kind").value("CORRECTION"))
        .andExpect(jsonPath("$[1].changedFields[0]").value("applyEnd"))
        .andExpect(jsonPath("$[1].changedFields[1]").value("summaryText"))
        .andExpect(jsonPath("$[1].receivedAt").value(org.hamcrest.Matchers.endsWith("+09:00")));
  }

  @Test
  void unknownNoticeIsNotFound() throws Exception {
    mvc.perform(get("/api/v1/notices/{id}/versions", UUID.randomUUID()))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOTICE_NOT_FOUND"));
  }
}
