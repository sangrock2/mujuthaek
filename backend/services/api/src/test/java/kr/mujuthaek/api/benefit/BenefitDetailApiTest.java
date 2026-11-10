package kr.mujuthaek.api.benefit;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.UUID;
import kr.mujuthaek.api.common.exception.GlobalExceptionHandlerAccess;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import tools.jackson.databind.node.ObjectNode;

class BenefitDetailApiTest {

  private final BenefitFixture f = new BenefitFixture();
  private final MockMvc mvc =
      MockMvcBuilders.standaloneSetup(
              kr.mujuthaek.api.benefit.controller.BenefitControllerAccess.controller(f.details))
          .setControllerAdvice(GlobalExceptionHandlerAccess.handler())
          .build();

  @Test
  void 상세는_원_단위_금액과_조건_원문_신청_상태를_준다() throws Exception {
    UUID id = f.benefit(p -> {});

    mvc.perform(get("/api/v1/benefits/{id}", id))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.header.title").value("청년 취업자 주거비 지원사업"))
        .andExpect(jsonPath("$.header.category").value("HOUSING"))
        .andExpect(jsonPath("$.header.applyStatus").value("APPLYING"))
        .andExpect(jsonPath("$.header.dday").value(39))
        .andExpect(jsonPath("$.header.regionCodes[0]").value("52730"))
        .andExpect(jsonPath("$.supports[0].amountMaxWon").value(200000))
        .andExpect(jsonPath("$.supports[0].months").value(12))
        .andExpect(jsonPath("$.conditions.length()").value(9))
        .andExpect(jsonPath("$.conditions[0].rawText").value("지원 대상 연령 18~49세"))
        .andExpect(jsonPath("$.howToApply").value("제출서류를 지참해 무주군청 인구활력과 방문 신청"))
        .andExpect(jsonPath("$.sources[0].sourceCode").value("youth"));
  }

  @Test
  void 지원_비율은_소수도_그대로_준다() throws Exception {
    // 「연 3.5% 이자 지원」: 정수로 바꾸면 3·4로 틀린 값이 돼요
    UUID id = f.benefit(p -> ((ObjectNode) p.path("supports").get(0)).put("ratePct", 3.5));

    mvc.perform(get("/api/v1/benefits/{id}", id))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.supports[0].ratePct").value(3.5));
  }

  @Test
  void 없거나_숨긴_혜택은_404() throws Exception {
    UUID hidden = f.benefit(p -> p.put("relevant", false));

    mvc.perform(get("/api/v1/benefits/{id}", hidden)).andExpect(status().isNotFound());
    mvc.perform(get("/api/v1/benefits/{id}", UUID.randomUUID()))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("BENEFIT_NOT_FOUND"));
  }
}
