package kr.mujuthaek.api.eligibility.controller;

import static kr.mujuthaek.api.notice.NoticeApiFixture.schedule;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Clock;
import java.time.ZoneId;
import java.util.UUID;
import kr.mujuthaek.api.benefit.repository.BenefitRepository;
import kr.mujuthaek.api.benefit.service.BenefitQueryService;
import kr.mujuthaek.api.eligibility.repository.CriteriaStore;
import kr.mujuthaek.api.eligibility.repository.LoanProductStore;
import kr.mujuthaek.api.eligibility.service.BenefitEvaluationService;
import kr.mujuthaek.api.eligibility.service.CriteriaService;
import kr.mujuthaek.api.eligibility.service.HomeSummaryService;
import kr.mujuthaek.api.eligibility.service.NoticeEvaluationService;
import kr.mujuthaek.api.eligibility.service.NoticeSearchService;
import kr.mujuthaek.api.eligibility.service.PrepareCostService;
import kr.mujuthaek.api.notice.NoticeApiFixture;
import kr.mujuthaek.api.notice.NoticeFixtures;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.node.ObjectNode;

/** 홈 요약: 맞춤 목록과 같은 판정에서 개수·새 공고·마감 임박을 골라요. 오늘은 2026-10-22로 고정이에요. */
class HomeSummaryApiTest {

  private final NoticeApiFixture f = new NoticeApiFixture();
  private final Clock clock =
      Clock.fixed(
          NoticeApiFixture.TODAY.atStartOfDay(ZoneId.of("Asia/Seoul")).toInstant(),
          ZoneId.of("Asia/Seoul"));
  private final CriteriaService criteria =
      new CriteriaService(
          new CriteriaStore(f.jdbc), new LoanProductStore(f.jdbc), NoticeFixtures.JSON, clock);
  private final NoticeEvaluationService evaluations =
      new NoticeEvaluationService(
          f.queries,
          criteria,
          new PrepareCostService(new LoanProductStore(f.jdbc), criteria, clock));
  private final MockMvc mvc =
      f.mvc(
          new HomeSummaryController(
              new HomeSummaryService(
                  new NoticeSearchService(
                      f.queries,
                      evaluations,
                      new kr.mujuthaek.api.eligibility.service.JudgingFrames(
                          f.queries,
                          new io.micrometer.core.instrument.simple.SimpleMeterRegistry(),
                          20000,
                          false)),
                  new BenefitEvaluationService(
                      new BenefitQueryService(
                          new BenefitRepository(
                              org.springframework.jdbc.core.simple.JdbcClient.create(f.jdbc))),
                      criteria,
                      NoticeFixtures.JSON,
                      clock,
                      new io.micrometer.core.instrument.simple.SimpleMeterRegistry(),
                      20000),
                  clock)));

  /** 나이 조건 하나짜리 공고. postedOn은 공고일(announcedOn)이에요. */
  private UUID notice(int minAge, int maxAge, String postedOn, String applyEnd) {
    return f.notice(
        p -> {
          schedule(p, "2026-10-01", applyEnd);
          ((ObjectNode) p.get("notice").get("notice")).put("announcedOn", postedOn);
          NoticeFixtures.judgment(
              p,
              NoticeFixtures.JSON.readTree(
                  """
                  {"schema":"housing-judgment.v1","rawPostId":"x","rawVersion":1,"referenceDate":"2026-10-01",
                   "common":[],"groups":[{"id":"youth","name":"청년","criteria":[
                     {"kind":"AGE","id":"age","quote":null,"page":null,"inReview":false,"reviewReason":null,
                      "minAge":%d,"maxAge":%d}]}],"notes":[]}"""
                      .formatted(minAge, maxAge)));
        });
  }

  @Test
  void countsNewsAndDeadlinesFromTheJudgedNotices() throws Exception {
    UUID fresh = notice(19, 39, "2026-10-20", "2026-10-25"); // 지원 가능 · 새 공고 · D-3
    UUID older = notice(19, 39, "2026-09-01", "2026-11-30"); // 지원 가능 · 오래된 공고 · D-39
    UUID tooOld = notice(40, 50, "2026-10-21", "2026-10-24"); // 지원 불가 (소식·마감에서 빼요)

    String body =
        """
        {"filters":{"providers":["%s"]},"applicant":{"birthMonth":"1997-03"}}"""
            .formatted(f.provider);
    var result =
        mvc.perform(
                post("/api/v1/home/summary").contentType(MediaType.APPLICATION_JSON).content(body))
            .andExpect(status().isOk())
            .andExpect(header().string("Cache-Control", "no-store"))
            .andExpect(jsonPath("$.homes.eligible").value(2))
            .andExpect(jsonPath("$.homes.ineligible").value(1))
            .andExpect(jsonPath("$.homes.newThisWeek").value(1))
            .andExpect(jsonPath("$.homes.closingSoon").value(1))
            .andExpect(jsonPath("$.news[0].id").value(fresh.toString()))
            .andExpect(jsonPath("$.news[1].id").value(older.toString()))
            .andExpect(jsonPath("$.news.length()").value(2))
            .andExpect(jsonPath("$.deadlines.length()").value(1))
            .andExpect(jsonPath("$.deadlines[0].id").value(fresh.toString()))
            .andExpect(jsonPath("$.deadlines[0].dday").value(3))
            .andExpect(jsonPath("$.deadlines[0].overall").value("ELIGIBLE"))
            .andReturn();

    String json = result.getResponse().getContentAsString();
    assertThat(json).doesNotContain(tooOld.toString(), "1997-03");
  }

  @Test
  void emptyBodyStillAnswers() throws Exception {
    mvc.perform(
            post("/api/v1/home/summary")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"filters":{"providers":["%s"]}}"""
                        .formatted(f.provider)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.homes.eligible").value(0))
        .andExpect(jsonPath("$.bestArea").doesNotExist())
        .andExpect(jsonPath("$.benefits.eligible").isNumber())
        .andExpect(jsonPath("$.news.length()").value(0));
  }

  @Test
  void badBandIs400() throws Exception {
    mvc.perform(
            post("/api/v1/home/summary")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"applicant\":{\"homelessYears\":\"2_4\"}}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.errors[0].field").value("applicant.homelessYears"));
  }
}
