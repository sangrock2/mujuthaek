package kr.mujuthaek.api.notice.controller;

import static kr.mujuthaek.api.notice.NoticeApiFixture.schedule;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.notice.NoticeApiFixture;
import kr.mujuthaek.api.notice.NoticeFixtures;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.node.ObjectNode;

class NoticeListApiTest {

  private final NoticeApiFixture f = new NoticeApiFixture();
  private final MockMvc mvc = f.mvc(new NoticeController(f.queries));

  @Test
  void listsOpenNoticesByDeadlineWithStatusAndDday() throws Exception {
    UUID soon = f.notice(p -> schedule(p, "2026-10-01", "2026-10-25"));
    UUID later = f.notice(p -> schedule(p, "2026-10-30", "2026-11-20"));
    f.notice(p -> schedule(p, "2026-09-01", "2026-10-01")); // 마감 — 기본 목록에서 빠져요

    mvc.perform(get("/api/v1/notices").param("providers", f.provider))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items.length()").value(2))
        .andExpect(jsonPath("$.items[0].id").value(soon.toString()))
        .andExpect(jsonPath("$.items[0].status").value("APPLYING"))
        .andExpect(jsonPath("$.items[0].dday").value(3))
        .andExpect(jsonPath("$.items[0].noticeType").value("PURCHASE_RENTAL"))
        .andExpect(jsonPath("$.items[1].id").value(later.toString()))
        .andExpect(jsonPath("$.items[1].status").value("UPCOMING"))
        .andExpect(jsonPath("$.hasNext").value(false))
        .andExpect(jsonPath("$.nextCursor").doesNotExist());
  }

  @Test
  void pagesWithTheCursorWithoutRepeatsOrGaps() throws Exception {
    for (int day = 23; day <= 27; day++) {
      int d = day;
      f.notice(p -> schedule(p, "2026-10-01", "2026-10-" + d));
    }

    List<String> seen = new java.util.ArrayList<>();
    String cursor = null;
    do {
      var request = get("/api/v1/notices").param("providers", f.provider).param("size", "2");
      if (cursor != null) {
        request.param("cursor", cursor);
      }
      String body = mvc.perform(request).andReturn().getResponse().getContentAsString();
      seen.addAll(JsonPath.read(body, "$.items[*].applyEnd"));
      cursor = JsonPath.read(body, "$.nextCursor");
    } while (cursor != null);

    assertThat(seen)
        .containsExactly("2026-10-23", "2026-10-24", "2026-10-25", "2026-10-26", "2026-10-27");
  }

  @Test
  void filtersByRegionTenureStatusAndType() throws Exception {
    UUID mapo = f.notice(p -> NoticeFixtures.region(p, "11440"));
    UUID suwon = f.notice(p -> NoticeFixtures.region(p, "41111"));
    UUID sale =
        f.notice(p -> ((ObjectNode) p.get("notice").get("notice")).put("supplyType", "공공분양"));
    // 유형을 못 정한 공고는 분양이 아니니 빌려서에 나와요
    UUID untyped =
        f.notice(p -> ((ObjectNode) p.get("notice").get("notice")).put("supplyType", "공공기숙사"));

    assertThat(ids("regionCodes", "11440")).containsExactly(mapo.toString());
    assertThat(ids("regionCodes", "41")).containsExactly(suwon.toString());
    // 2026-11-10 재검토: 수원시(41110)를 고르면 장안구(41111) 공고가 빠지고, 증평군(43745)을 고르면 영동군(43740) 전체 공고가 나왔음
    assertThat(ids("regionCodes", "41110")).containsExactly(suwon.toString());
    UUID yeongdong = f.notice(p -> NoticeFixtures.region(p, "43740"));
    assertThat(ids("regionCodes", "43745")).isEmpty();
    assertThat(ids("regionCodes", "43740")).containsExactly(yeongdong.toString());
    assertThat(ids("tenure", "BUY")).containsExactly(sale.toString());
    assertThat(ids("noticeTypes", "PUBLIC_SALE")).containsExactly(sale.toString());
    assertThat(ids("tenure", "RENT"))
        .doesNotContain(sale.toString())
        .contains(mapo.toString(), untyped.toString());
    assertThat(ids("statuses", "CLOSED")).isEmpty();
  }

  @Test
  void filtersByDeadlineRange() throws Exception {
    UUID early = f.notice(p -> schedule(p, "2026-10-01", "2026-10-25"));
    UUID mid = f.notice(p -> schedule(p, "2026-10-01", "2026-11-10"));
    f.notice(p -> schedule(p, "2026-10-01", "2026-12-20"));

    assertThat(deadline("2026-11-01", "2026-11-30")).containsExactly(mid.toString());
    assertThat(deadline(null, "2026-11-10")).containsExactly(early.toString(), mid.toString());
    mvc.perform(
            get("/api/v1/notices")
                .param("applyEndFrom", "2026-12-01")
                .param("applyEndTo", "2026-11-01"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
  }

  private List<String> deadline(String from, String to) throws Exception {
    var request = get("/api/v1/notices").param("providers", f.provider);
    if (from != null) {
      request.param("applyEndFrom", from);
    }
    if (to != null) {
      request.param("applyEndTo", to);
    }
    String body = mvc.perform(request).andReturn().getResponse().getContentAsString();
    return JsonPath.read(body, "$.items[*].id");
  }

  @Test
  void latestSortUsesPostedOn() throws Exception {
    UUID older =
        f.notice(
            p -> ((ObjectNode) p.get("notice").get("notice")).put("announcedOn", "2026-09-01"));
    UUID newer =
        f.notice(
            p -> ((ObjectNode) p.get("notice").get("notice")).put("announcedOn", "2026-10-20"));

    assertThat(ids("sort", "LATEST")).containsExactly(newer.toString(), older.toString());
  }

  @Test
  void rejectsUnknownFilterValuesAndCursorsFromAnotherSort() throws Exception {
    mvc.perform(get("/api/v1/notices").param("statuses", "OPEN"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
    mvc.perform(get("/api/v1/notices").param("regionCodes", "114"))
        .andExpect(status().isBadRequest());

    for (int i = 0; i < 2; i++) {
      f.notice(p -> {});
    }
    String body =
        mvc.perform(get("/api/v1/notices").param("providers", f.provider).param("size", "1"))
            .andReturn()
            .getResponse()
            .getContentAsString();
    String cursor = JsonPath.read(body, "$.nextCursor");
    mvc.perform(get("/api/v1/notices").param("sort", "LATEST").param("cursor", cursor))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("INVALID_CURSOR"));
  }

  @Test
  void hiddenAndUnpublishedNoticesAreNotListed() throws Exception {
    UUID hidden = f.notice(p -> {});
    f.jdbc.update("update notice.notices set hidden = true where id = ?", hidden);
    f.notice(p -> p.put("reviewStatus", "IN_REVIEW"));

    assertThat(ids("providers", f.provider)).isEmpty();
  }

  private List<String> ids(String name, String value) throws Exception {
    var request = get("/api/v1/notices").param("providers", f.provider);
    if (!name.equals("providers")) {
      request.param(name, value);
    }
    String body = mvc.perform(request).andReturn().getResponse().getContentAsString();
    return JsonPath.read(body, "$.items[*].id");
  }
}
