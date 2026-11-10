package kr.mujuthaek.api.eligibility.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Clock;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.mapper.JudgmentReaderTest;
import kr.mujuthaek.api.eligibility.repository.CriteriaStore;
import kr.mujuthaek.api.eligibility.repository.LoanProductStore;
import kr.mujuthaek.api.eligibility.service.CriteriaService;
import kr.mujuthaek.api.eligibility.service.NoticeEvaluationService;
import kr.mujuthaek.api.eligibility.service.PrepareCostService;
import kr.mujuthaek.api.eligibility.service.SubscriptionScoreService;
import kr.mujuthaek.api.notice.NoticeApiFixture;
import kr.mujuthaek.api.notice.NoticeFixtures;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

/** 판정 틀(계약의 서리풀 판정 예시)이 든 공고를 실제 DB에 저장하고 판정해요. */
class NoticeEvaluateApiTest {

  private final NoticeApiFixture f = new NoticeApiFixture();
  private final CriteriaService criteria =
      new CriteriaService(
          new CriteriaStore(f.jdbc),
          new LoanProductStore(f.jdbc),
          NoticeFixtures.JSON,
          Clock.systemUTC());
  private final PrepareCostService prepareCost =
      new PrepareCostService(new LoanProductStore(f.jdbc), criteria, Clock.systemUTC());
  private final MockMvc mvc =
      f.mvc(
          new EligibilityController(
              criteria,
              mock(SubscriptionScoreService.class),
              new NoticeEvaluationService(f.queries, criteria, prepareCost),
              prepareCost));

  @org.junit.jupiter.api.BeforeEach
  void loans() {
    // 테스트용 상품 (실제 한도는 관리자가 넣어요): 보증금의 70%, 최대 1억 2천만 원, 조건 없음
    f.jdbc.update("delete from eligibility.loan_products");
    f.jdbc.update(
        "insert into eligibility.loan_products (code, name, max_amount_won, deposit_ratio)"
            + " values ('GENERAL', '일반 전세자금', 120000000, 0.7)");
  }

  @Test
  void unitTypesShowWhatToPrepare() throws Exception {
    UUID id = noticeWithJudgment();

    mvc.perform(
            post("/api/v1/eligibility/notices/{id}/evaluate", id)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"applicant\":{}}"))
        .andExpect(jsonPath("$.unitTypes[0].houseType").value("20A"))
        .andExpect(jsonPath("$.unitTypes[0].eligible").value(false))
        .andExpect(jsonPath("$.unitTypes[0].prepareCost.depositWon").value(1000000))
        .andExpect(jsonPath("$.unitTypes[0].prepareCost.loan.productCode").value("GENERAL"))
        .andExpect(jsonPath("$.unitTypes[0].prepareCost.loan.amountWon").value(700000))
        .andExpect(jsonPath("$.unitTypes[0].prepareCost.prepareWon").value(300000))
        // 쓸 수 있는 돈과 비교는 화면이 해요 (서버는 받지 않아요)
        .andExpect(jsonPath("$.unitTypes[0].prepareCost.shortageWon").doesNotExist());
  }

  @Test
  void prepareCostForADeposit() throws Exception {
    mvc.perform(
            post("/api/v1/eligibility/prepare-cost")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"applicant\":{},\"depositWon\":24000000}"))
        .andExpect(status().isOk())
        .andExpect(header().string("Cache-Control", "no-store"))
        .andExpect(jsonPath("$.prepareWon").value(7200000))
        .andExpect(jsonPath("$.shortageWon").doesNotExist());
    mvc.perform(
            post("/api/v1/eligibility/prepare-cost")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"applicant\":{}}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.errors[0].field").value("depositWon"));
  }

  private UUID noticeWithJudgment() {
    return f.notice(
        p -> {
          try {
            NoticeFixtures.judgment(p, JudgmentReaderTest.example());
          } catch (Exception e) {
            throw new IllegalStateException(e);
          }
        });
  }

  @Test
  void judgesByTargetAndNeverEchoesTheIncome() throws Exception {
    UUID id = noticeWithJudgment();
    String body =
        """
        {"applicant":{"birthDate":"1997-03-15","regionCode":"11650","homeOwner":false,"homelessYears":"3_5",
                      "householdSize":1,"income":{"URBAN_WORKER_INCOME":{"gtPct":31,"lePct":40}}}}""";

    var result =
        mvc.perform(
                post("/api/v1/eligibility/notices/{id}/evaluate", id)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body))
            .andExpect(status().isOk())
            .andExpect(header().string("Cache-Control", "no-store"))
            .andExpect(jsonPath("$.noticeId").value(id.toString()))
            .andExpect(jsonPath("$.overall").value("NEEDS_INPUT"))
            .andExpect(jsonPath("$.targets[0].name").value("문화예술분야 청년예술인"))
            .andExpect(jsonPath("$.targets[0].overall").value("NEEDS_INPUT"))
            .andExpect(jsonPath("$.targets[0].items[0].key").value("ASK"))
            .andExpect(jsonPath("$.targets[0].items[1].key").value("AGE"))
            .andExpect(jsonPath("$.targets[0].items[1].status").value("MET"))
            .andExpect(jsonPath("$.targets[0].items[1].evidence.text").exists())
            .andReturn();

    assertThat(result.getResponse().getContentAsString())
        .doesNotContain("1997-03", "gtPct", "lePct", "\"31\"");
  }

  @Test
  void noticesWithoutAJudgmentNeedTheOriginalChecked() throws Exception {
    UUID id = f.notice(p -> {});

    mvc.perform(
            post("/api/v1/eligibility/notices/{id}/evaluate", id)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"applicant\":{}}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.overall").value("NEEDS_INPUT"))
        .andExpect(jsonPath("$.reason").exists())
        .andExpect(jsonPath("$.targets.length()").value(0));
  }

  @Test
  void unknownNoticeAndBadInput() throws Exception {
    mvc.perform(
            post("/api/v1/eligibility/notices/{id}/evaluate", UUID.randomUUID())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"applicant\":{}}"))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOTICE_NOT_FOUND"));
    mvc.perform(
            post("/api/v1/eligibility/notices/{id}/evaluate", noticeWithJudgment())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"applicant\":{\"assets\":{\"gtWon\":-1}}}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.errors[0].field").value("applicant.assets.gtWon"));
  }
}
