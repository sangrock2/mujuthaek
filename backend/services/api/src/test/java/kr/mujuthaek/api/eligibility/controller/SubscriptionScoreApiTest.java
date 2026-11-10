package kr.mujuthaek.api.eligibility.controller;

import static org.mockito.Mockito.mock;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;
import kr.mujuthaek.api.common.exception.GlobalExceptionHandlerAccess;
import kr.mujuthaek.api.eligibility.service.CriteriaService;
import kr.mujuthaek.api.eligibility.service.SubscriptionScoreService;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class SubscriptionScoreApiTest {

  private final ZoneId seoul = ZoneId.of("Asia/Seoul");
  private final MockMvc mvc =
      MockMvcBuilders.standaloneSetup(
              new EligibilityController(
                  mock(CriteriaService.class),
                  new SubscriptionScoreService(
                      Clock.fixed(
                          LocalDate.of(2026, 10, 22).atStartOfDay(seoul).toInstant(), seoul)),
                  mock(kr.mujuthaek.api.eligibility.service.NoticeEvaluationService.class),
                  mock(kr.mujuthaek.api.eligibility.service.PrepareCostService.class)))
          .setControllerAdvice(GlobalExceptionHandlerAccess.handler())
          .build();

  @Test
  void scoresAndNeverCaches() throws Exception {
    String body =
        """
        {"applicant":{"birthDate":"1980-03-15","marital":"SINGLE","homelessSince":"2015-01",
                      "dependents":2,"subscription":{"joinedOn":"2016-03"}}}""";

    mvc.perform(
            post("/api/v1/eligibility/subscription-score")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
        .andExpect(status().isOk())
        .andExpect(header().string("Cache-Control", "no-store"))
        .andExpect(jsonPath("$.total").value(51))
        .andExpect(jsonPath("$.max").value(84))
        .andExpect(jsonPath("$.items[0].key").value("HOMELESS_PERIOD"))
        .andExpect(jsonPath("$.items[0].points").value(24))
        .andExpect(jsonPath("$.items[0].max").value(32))
        .andExpect(jsonPath("$.items[1].points").value(15))
        .andExpect(jsonPath("$.items[2].points").value(12));
  }

  @Test
  void referenceDateMovesTheCount() throws Exception {
    String body =
        """
        {"applicant":{"dependents":0,"subscription":{"joinedOn":"2016-03"}},"referenceDate":"2017-04-01"}""";

    mvc.perform(
            post("/api/v1/eligibility/subscription-score")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
        .andExpect(jsonPath("$.items[2].points").value(3))
        .andExpect(jsonPath("$.missingInputs[0]").value("applicant.birthDate"));
  }

  @Test
  void invalidInputIsRejectedWithoutTheValue() throws Exception {
    mvc.perform(
            post("/api/v1/eligibility/subscription-score")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"applicant\":{\"dependents\":-4}}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.errors[0].field").value("applicant.dependents"))
        .andExpect(jsonPath("$.errors[0].reason").value("MIN"));
    mvc.perform(
            post("/api/v1/eligibility/subscription-score")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.errors[0].field").value("applicant"));
  }
}
