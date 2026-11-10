package kr.mujuthaek.api.eligibility.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import java.util.List;
import java.util.UUID;
import java.util.function.Consumer;
import kr.mujuthaek.api.benefit.BenefitFixture;
import kr.mujuthaek.api.common.exception.GlobalExceptionHandlerAccess;
import kr.mujuthaek.api.eligibility.repository.CriteriaStore;
import kr.mujuthaek.api.eligibility.repository.LoanProductStore;
import kr.mujuthaek.api.eligibility.service.BenefitEvaluationService;
import kr.mujuthaek.api.eligibility.service.BenefitSearchService;
import kr.mujuthaek.api.eligibility.service.CriteriaService;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import tools.jackson.databind.node.ObjectNode;

/** 혜택 맞춤 목록·판정. 오늘은 2026-10-22 고정. 지역은 테스트마다 다른 시군구라 다른 테스트의 혜택과 섞이지 않아요. */
class BenefitSearchApiTest {

  private final BenefitFixture f = new BenefitFixture();
  private final CriteriaService criteria =
      new CriteriaService(
          new CriteriaStore(f.jdbc), new LoanProductStore(f.jdbc), BenefitFixture.JSON, f.clock);
  private final BenefitEvaluationService evaluations =
      new BenefitEvaluationService(
          f.queries,
          criteria,
          BenefitFixture.JSON,
          f.clock,
          new io.micrometer.core.instrument.simple.SimpleMeterRegistry(),
          20000);
  private final MockMvc mvc =
      MockMvcBuilders.standaloneSetup(
              new BenefitSearchController(new BenefitSearchService(evaluations), evaluations))
          .setControllerAdvice(GlobalExceptionHandlerAccess.handler())
          .build();

  @org.junit.jupiter.api.BeforeEach
  void onlyThisTestsRegion() {
    // 전국·시도·지역 모름(UNKNOWN, 확인 필요로 어디에나 나옴) 혜택은 이 테스트의 시군구 검색에도 섞여 개수가 바뀌어요.
    // 다른 테스트가 만든 것까지 숨겨요 (테스트 순서에 따라 가끔 categoryCounts가 1 많던 문제)
    f.jdbc.update("update benefit.benefits set status = 'HIDDEN' where region_scope <> 'SIGUNGU'");
  }

  /** 이 시군구만 대상인 혜택 (나이 조건 하나 + 월 20만 원 12개월). */
  private UUID benefit(String region, int minAge, int maxAge, Consumer<ObjectNode> more) {
    return f.benefit(
        p -> {
          var source = p.withObject("source");
          source.put("regionScope", "SIGUNGU");
          source.putArray("regionCodes").add(region);
          var conditions = p.putArray("conditions");
          conditions
              .addObject()
              .put("type", "AGE")
              .put("group", 1)
              .put("known", true)
              .put("origin", "RULE")
              .put("rawText", "만 " + minAge + "~" + maxAge + "세")
              .put("evidence", "나이")
              .put("confidence", 1)
              .putObject("value")
              .put("min", minAge)
              .put("max", maxAge);
          more.accept(p);
        });
  }

  private String body(String region, String extra) {
    return """
        {"filters":{"regionCodes":["%s"]},"applicant":{"birthMonth":"1997-03","regionCode":"%s"}%s}"""
        .formatted(region, region, extra);
  }

  @Test
  void 판정하고_지원_불가를_빼고_1년_금액을_더한다() throws Exception {
    String region = "4" + (int) (Math.random() * 9000 + 1000);
    UUID ok = benefit(region, 19, 39, p -> {});
    UUID loan =
        benefit(
            region,
            19,
            39,
            p -> {
              var s = (ObjectNode) p.withArray("supports").get(0);
              s.put("kind", "DEPOSIT_LOAN").put("amountMax", 10000).put("amountPer", "ONCE");
              s.putNull("months").putNull("ratePct");
            });
    UUID no = benefit(region, 40, 60, p -> {});

    var result =
        mvc.perform(
                post("/api/v1/benefits/search")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body(region, "")))
            .andExpect(status().isOk())
            .andExpect(header().string("Cache-Control", "no-store"))
            .andExpect(jsonPath("$.summary.eligible").value(2))
            .andExpect(jsonPath("$.summary.ineligible").value(1))
            .andExpect(jsonPath("$.summary.annualAmountWon").value(2_400_000))
            .andExpect(jsonPath("$.categoryCounts.HOUSING").value(2))
            .andReturn()
            .getResponse()
            .getContentAsString();
    List<String> ids = JsonPath.read(result, "$.items[*].id");
    assertThat(ids).containsExactly(ok.toString(), loan.toString()).doesNotContain(no.toString());
    assertThat((String) JsonPath.read(result, "$.items[0].amountText"))
        .isEqualTo("월 최대 20만 원 · 12개월");
    assertThat((Boolean) JsonPath.read(result, "$.items[1].affectsPrepareCost")).isTrue();
    assertThat((String) JsonPath.read(result, "$.items[1].amountText")).isEqualTo("최대 1억 원 대출");
    assertThat(result).doesNotContain("1997-03");
  }

  @Test
  void 혜택_하나를_그룹별로_판정한다() throws Exception {
    String region = "4" + (int) (Math.random() * 9000 + 1000);
    UUID id = benefit(region, 19, 39, p -> {});

    mvc.perform(
            post("/api/v1/benefits/{id}/evaluate", id)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"applicant\":{\"birthMonth\":\"1997-03\"}}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.overall").value("ELIGIBLE"))
        .andExpect(jsonPath("$.conditions[0].items[0].key").value("AGE"))
        .andExpect(jsonPath("$.conditions[0].items[0].status").value("MET"))
        .andExpect(jsonPath("$.annualAmountWon").value(2_400_000));

    mvc.perform(
            post("/api/v1/benefits/{id}/evaluate", UUID.randomUUID())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"applicant\":{}}"))
        .andExpect(status().isNotFound());
  }

  @Test
  void 잘못된_분야와_정렬은_400() throws Exception {
    mvc.perform(
            post("/api/v1/benefits/search")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"filters\":{\"categories\":[\"FOOD\"]},\"sort\":\"CHEAP\"}"))
        .andExpect(status().isBadRequest());
  }
}
