package kr.mujuthaek.api.notice.controller;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.UUID;
import kr.mujuthaek.api.notice.NoticeApiFixture;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;

/** 계약 예시(contracts/examples/extraction.completed.json)를 저장하고 상세 묶음을 확인해요. */
class NoticeDetailApiTest {

  private final NoticeApiFixture f = new NoticeApiFixture();
  private final MockMvc mvc = f.mvc(new NoticeController(f.queries));

  @Test
  void detailBundlesComeFromTheCurrentVersion() throws Exception {
    UUID id = f.notice(p -> {});

    mvc.perform(get("/api/v1/notices/{id}", id))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.header.id").value(id.toString()))
        .andExpect(jsonPath("$.header.title").value("가상주거 청년 매입임대 입주자 모집 공고"))
        .andExpect(jsonPath("$.header.noticeType").value("PURCHASE_RENTAL"))
        .andExpect(jsonPath("$.header.supplyTypeText").value("매입임대"))
        .andExpect(jsonPath("$.header.status").value("APPLYING"))
        .andExpect(jsonPath("$.header.dday").value(9))
        .andExpect(jsonPath("$.header.detailUrl").value("https://example.org/notices/housing-1"))
        .andExpect(jsonPath("$.summary.summaryText").value("테스트 전용 가상 공고입니다."))
        .andExpect(jsonPath("$.summary.targetGroups[0]").value("YOUTH"))
        .andExpect(jsonPath("$.summary.supplyTotal").value(1))
        .andExpect(jsonPath("$.schedules[0].label").value("신청"))
        .andExpect(jsonPath("$.schedules[0].startsAt").value("2026-10-01T10:00:00+09:00"))
        .andExpect(jsonPath("$.schedules[0].current").value(true))
        .andExpect(jsonPath("$.schedules[0].channels[0]").value("ONLINE"))
        .andExpect(jsonPath("$.schedules[0].places.length()").value(0))
        .andExpect(jsonPath("$.schedules[0].applicationEmail").doesNotExist())
        .andExpect(jsonPath("$.schedules[0].excludedDays.length()").value(0))
        .andExpect(jsonPath("$.summary.applicationChannels[0]").value("ONLINE"))
        .andExpect(jsonPath("$.requiredDocuments[0].name").value("주민등록등본"))
        .andExpect(jsonPath("$.requiredDocuments[0].group").doesNotExist())
        .andExpect(jsonPath("$.requiredDocuments[0].evidence.length()").value(1))
        .andExpect(jsonPath("$.selectionRules.length()").value(2))
        .andExpect(jsonPath("$.selectionRules[0].kind").value("PRIORITY"))
        .andExpect(jsonPath("$.selectionRules[0].priorityRank").value(1))
        .andExpect(jsonPath("$.guidance[0].kind").value("APPLICATION_METHOD"))
        .andExpect(jsonPath("$.guidance[0].title").value("온라인 신청"))
        .andExpect(jsonPath("$.sites[0].name").value("가상건물 A동"))
        .andExpect(jsonPath("$.sites[0].regionCode").value("11110"))
        .andExpect(jsonPath("$.unitTypes[0].houseType").value("20A"))
        .andExpect(jsonPath("$.unitTypes[0].exclusiveM2").value(20))
        .andExpect(jsonPath("$.unitTypes[0].depositWon").value(1000000))
        .andExpect(jsonPath("$.unitTypes[0].rentWon").value(100000))
        .andExpect(jsonPath("$.unitTypes[0].supplyCount").value(1))
        .andExpect(
            jsonPath("$.unitTypes[0].evidence[0].documentName").value("housing.synthetic.txt"))
        .andExpect(jsonPath("$.schedules[0].evidence[0].quote").value(startsWith("테스트 전용 가상 공고")))
        .andExpect(jsonPath("$.schedules[0].evidence[0].page").doesNotExist())
        .andExpect(jsonPath("$.conditions[0].evidence.length()").value(1))
        .andExpect(jsonPath("$.conditions.length()").value(3))
        .andExpect(jsonPath("$.conditions[0].category").value("AGE"))
        .andExpect(
            jsonPath("$.conditions[0].originalText").value("공고일 만 19세 이상 39세 이하이며 무주택 가구여야 합니다."))
        .andExpect(
            jsonPath("$.files[0].url").value("https://example.org/documents/housing.synthetic.txt"))
        .andExpect(jsonPath("$.hasUnits").value(true))
        .andExpect(jsonPath("$.version").value(1))
        .andExpect(jsonPath("$.reviewed").value(false))
        .andExpect(jsonPath("$.updatedAt").value(org.hamcrest.Matchers.endsWith("+09:00")));
  }

  @Test
  void hiddenUnpublishedAndUnknownNoticesAreNotFound() throws Exception {
    UUID hidden = f.notice(p -> {});
    f.jdbc.update("update notice.notices set hidden = true where id = ?", hidden);
    UUID inReview = f.notice(p -> p.put("reviewStatus", "IN_REVIEW"));

    for (UUID id : new UUID[] {hidden, inReview, UUID.randomUUID()}) {
      mvc.perform(get("/api/v1/notices/{id}", id))
          .andExpect(status().isNotFound())
          .andExpect(jsonPath("$.code").value("NOTICE_NOT_FOUND"));
    }
    mvc.perform(get("/api/v1/notices/not-a-uuid"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
  }
}
