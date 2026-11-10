package kr.mujuthaek.api.eligibility.controller;

import static kr.mujuthaek.api.notice.NoticeApiFixture.schedule;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import java.time.Clock;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.repository.CriteriaStore;
import kr.mujuthaek.api.eligibility.repository.LoanProductStore;
import kr.mujuthaek.api.eligibility.service.CriteriaService;
import kr.mujuthaek.api.eligibility.service.NoticeEvaluationService;
import kr.mujuthaek.api.eligibility.service.NoticeSearchService;
import kr.mujuthaek.api.eligibility.service.PrepareCostService;
import kr.mujuthaek.api.notice.NoticeApiFixture;
import kr.mujuthaek.api.notice.NoticeFixtures;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.node.ObjectNode;

class NoticeSearchApiTest {

  private final NoticeApiFixture f = new NoticeApiFixture();
  private final CriteriaService criteria =
      new CriteriaService(
          new CriteriaStore(f.jdbc),
          new LoanProductStore(f.jdbc),
          NoticeFixtures.JSON,
          Clock.systemUTC());
  private final NoticeEvaluationService evaluations =
      new NoticeEvaluationService(
          f.queries,
          criteria,
          new PrepareCostService(new LoanProductStore(f.jdbc), criteria, Clock.systemUTC()));
  private final MockMvc mvc =
      f.mvc(
          new NoticeSearchController(
              new NoticeSearchService(
                  f.queries,
                  evaluations,
                  new kr.mujuthaek.api.eligibility.service.JudgingFrames(
                      f.queries,
                      new io.micrometer.core.instrument.simple.SimpleMeterRegistry(),
                      20000,
                      false))));

  @org.junit.jupiter.api.BeforeEach
  void noLoans() {
    f.jdbc.update("delete from eligibility.loan_products"); // 대출이 없으면 준비할 돈 = 보증금
  }

  /** 나이 조건 하나짜리 판정 틀. */
  private UUID noticeForAges(int min, int max, String applyEnd) {
    return f.notice(
        p -> {
          schedule(p, "2026-10-01", applyEnd);
          NoticeFixtures.judgment(
              p,
              NoticeFixtures.JSON.readTree(
                  """
                  {"schema":"housing-judgment.v1","rawPostId":"x","rawVersion":1,"referenceDate":"2026-10-01",
                   "common":[],"groups":[{"id":"youth","name":"청년","criteria":[
                     {"kind":"AGE","id":"age","quote":null,"page":null,"inReview":false,"reviewReason":null,
                      "minAge":%d,"maxAge":%d}]}],"notes":[]}"""
                      .formatted(min, max)));
        });
  }

  private String body(String extra) {
    return """
        {"filters":{"providers":["%s"]},"applicant":{"birthMonth":"1997-03"}%s}"""
        .formatted(f.provider, extra);
  }

  @Test
  void alwaysOpenNoticesAreIncludedByDefaultLikeThePublicList() throws Exception {
    UUID always =
        f.notice(
            p -> {
              schedule(p, null, null);
              ((ObjectNode) p.get("notice").get("schedules").get(0))
                  .put("applicationMode", "ROLLING"); // 원문이 수시 모집 → 상시
              NoticeFixtures.project(p);
            });
    UUID undated = f.notice(p -> schedule(p, null, null)); // 날짜만 없음 → 확인 필요(UNKNOWN)

    mvc.perform(
            post("/api/v1/notices/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body("")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items[?(@.id == '%s')].status".formatted(always)).value("ALWAYS"))
        .andExpect(jsonPath("$.items[?(@.id == '%s')].status".formatted(undated)).value("UNKNOWN"));
  }

  @Test
  void keywordKeepsOnlyNoticesWhoseTitleHasEveryWord() throws Exception {
    UUID mapo = noticeForAges(19, 39, "2026-10-30");
    UUID other = noticeForAges(19, 39, "2026-10-30");
    title(mapo, "마포 행복주택 입주자 모집");
    title(other, "강남 행복주택 입주자 모집");

    mvc.perform(
            post("/api/v1/notices/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"filters":{"providers":["%s"],"keyword":"행복 주택  마포"},"applicant":{"birthMonth":"1997-03"}}"""
                        .formatted(f.provider)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items.length()").value(1))
        .andExpect(jsonPath("$.items[0].id").value(mapo.toString()));
  }

  private void title(UUID notice, String title) {
    f.jdbc.update("update notice.notices set title = ? where id = ?", title, notice);
  }

  @Test
  void craftedPositionCursorIs400Not500() throws Exception {
    noticeForAges(19, 39, "2026-10-30");
    String cursor =
        kr.mujuthaek.api.common.pagination.CursorCodec.encode(
            new kr.mujuthaek.api.common.pagination.CursorKey(
                "RECOMMENDED", "-5", UUID.randomUUID()));

    mvc.perform(
            post("/api/v1/notices/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body(",\"cursor\":\"" + cursor + "\"")))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("INVALID_CURSOR"));
  }

  @Test
  void judgesEachNoticeAndPutsEligibleFirst() throws Exception {
    UUID unknown = f.notice(p -> schedule(p, "2026-10-01", "2026-10-24")); // 판정 틀 없음 → 확인 필요
    UUID eligible = noticeForAges(19, 39, "2026-10-30");
    UUID ineligible = noticeForAges(40, 60, "2026-10-25");

    var result =
        mvc.perform(
                post("/api/v1/notices/search")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body("")))
            .andExpect(status().isOk())
            .andExpect(header().string("Cache-Control", "no-store"))
            .andExpect(jsonPath("$.counts.eligible").value(1))
            .andExpect(jsonPath("$.counts.needsInput").value(1))
            .andExpect(jsonPath("$.counts.ineligible").value(1))
            .andExpect(jsonPath("$.items[0].overall").value("ELIGIBLE"))
            .andExpect(jsonPath("$.items[0].prepareCostWon").value(1000000))
            .andReturn();
    List<String> ids = JsonPath.read(result.getResponse().getContentAsString(), "$.items[*].id");
    assertThat(ids).containsExactly(eligible.toString(), unknown.toString());

    String all =
        mvc.perform(
                post("/api/v1/notices/search")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body(",\"includeIneligible\":true,\"sort\":\"DEADLINE\"")))
            .andReturn()
            .getResponse()
            .getContentAsString();
    assertThat((List<String>) JsonPath.read(all, "$.items[*].id"))
        .containsExactly(unknown.toString(), ineligible.toString(), eligible.toString());
  }

  /** area가 계산해 둔 생활권 점수(교통 한 항목)를 시험 DB에 직접 넣어요. 좌표는 동해 바다 위예요. */
  private void areaScore(UUID notice, int transit) {
    UUID site =
        f.jdbc.queryForObject(
            "insert into area.notice_locations (notice_id, notice_location_id, notice_version, kind,"
                + " address_text, geom, status, method) values (?, 'building-a', 1, 'BUILDING', '주소',"
                + " st_makepoint(132.1, 38.1)::geography, 'OK', 'FILE') returning location_id",
            UUID.class,
            notice);
    f.jdbc.update(
        "insert into area.location_scores (location_id, score_kind, category, score, score_version)"
            + " values (?, 'LIFE', 'TRANSIT', ?, '2026.1')",
        site,
        transit);
  }

  @Test
  void areaScoreSortPutsTheBetterAreaFirst() throws Exception {
    UUID soonLow = noticeForAges(19, 39, "2026-10-30");
    UUID laterHigh = noticeForAges(19, 39, "2026-11-30");
    areaScore(soonLow, 30);
    areaScore(laterHigh, 90);

    String body =
        mvc.perform(
                post("/api/v1/notices/search")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body(",\"sort\":\"AREA_SCORE\"")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items[0].areaScore").value(90))
            .andReturn()
            .getResponse()
            .getContentAsString();
    assertThat((List<String>) JsonPath.read(body, "$.items[*].id"))
        .containsExactly(laterHigh.toString(), soonLow.toString());
  }

  @Test
  void pagesAndRejectsBadValues() throws Exception {
    noticeForAges(19, 39, "2026-10-30");
    noticeForAges(19, 39, "2026-10-31");

    String first =
        mvc.perform(
                post("/api/v1/notices/search")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body(",\"size\":1")))
            .andReturn()
            .getResponse()
            .getContentAsString();
    String cursor = JsonPath.read(first, "$.nextCursor");
    mvc.perform(
            post("/api/v1/notices/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body(",\"size\":1,\"cursor\":\"" + cursor + "\"")))
        .andExpect(jsonPath("$.items[0].applyEnd").value("2026-10-31"))
        .andExpect(jsonPath("$.hasNext").value(false));

    mvc.perform(
            post("/api/v1/notices/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body(",\"sort\":\"CHEAPEST\"")))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.errors[0].field").value("sort"));
  }
}
