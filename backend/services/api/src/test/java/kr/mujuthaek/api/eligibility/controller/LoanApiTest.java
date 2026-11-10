package kr.mujuthaek.api.eligibility.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.empty;
import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.not;
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import kr.mujuthaek.api.TestcontainersConfiguration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

/**
 * 대출 자격 판정 API를 실제 스프링·DB(Testcontainers, 대출 상품 마이그레이션)로 불러요. 요청 → 상품별 결과·이유 → 응답, 캐시 금지, 오류 형식,
 * 로그까지 봐요.
 */
@SpringBootTest
@Import(TestcontainersConfiguration.class)
@ExtendWith(OutputCaptureExtension.class)
class LoanApiTest {

  private static final String PATH = "/api/v1/eligibility/loans/evaluate";

  @Autowired private WebApplicationContext context;
  private MockMvc mvc;

  @BeforeEach
  void setUp() {
    mvc = MockMvcBuilders.webAppContextSetup(context).build();
  }

  private ResultActions call(String profile) throws Exception {
    return mvc.perform(
        post(PATH)
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"asOf\": \"2026-10-21\", \"profile\": " + profile + "}"));
  }

  // 만 27세 미혼 1인 세대, 무주택, 연소득 4천만 원, 순자산 1억 원, 자녀 없음, 생애최초
  private static final String YOUTH =
      """
      {"birthDate": "1999-05-05", "maritalStatus": "SINGLE", "childBirthDates": [],
       "household": {"size": 1, "homeless": true},
       "loan": {"annualIncomeWon": 40000000, "applicantAnnualIncomeWon": 40000000,
                "netAssetWon": 100000000, "firstHomePurchase": true}}""";

  @Test
  void judgesEveryProductWithReasons() throws Exception {
    call(YOUTH)
        .andExpect(status().isOk())
        .andExpect(header().string("Cache-Control", "no-store"))
        .andExpect(jsonPath("$.asOf").value("2026-10-21"))
        .andExpect(jsonPath("$.items", hasSize(10)))
        .andExpect(jsonPath("$.counts.eligible").value(4))
        .andExpect(jsonPath("$.counts.needsInput").value(1))
        .andExpect(jsonPath("$.counts.ineligible").value(5))
        // 지원 가능이 먼저, 같은 상태끼리는 전세 → 월세 → 구입
        .andExpect(jsonPath("$.items[0].productCode").value("BEOTIMMOK_GENERAL"))
        .andExpect(jsonPath("$.items[0].loanType").value("JEONSE"))
        .andExpect(jsonPath("$.items[1].productCode").value("BEOTIMMOK_YOUTH"))
        .andExpect(jsonPath("$.items[1].status").value("ELIGIBLE"))
        .andExpect(jsonPath("$.items[1].failedConditions", empty()))
        .andExpect(jsonPath("$.items[1].limitSummary").value(containsString("1.5억 원")))
        .andExpect(jsonPath("$.items[1].rateSummary").value("연 2.2~3.3%"))
        .andExpect(
            jsonPath("$.items[1].sourceUrl")
                .value("https://nhuf.molit.go.kr/FP/FP05/FP0502/FP05020301.jsp"))
        // 확인 필요: 청년 주택드림 (청약 당첨은 입력으로 알 수 없어요)
        .andExpect(jsonPath("$.items[4].productCode").value("DIDIMDOL_YOUTH_DREAM"))
        .andExpect(jsonPath("$.items[4].status").value("NEEDS_INPUT"))
        .andExpect(jsonPath("$.items[4].checkReasons[0]").value(containsString("청년 주택드림 통장")))
        // 불가: 이유가 있고, 넣을 입력은 보여 주지 않아요
        .andExpect(jsonPath("$.items[5].productCode").value("BEOTIMMOK_NEWLYWED"))
        .andExpect(jsonPath("$.items[5].status").value("INELIGIBLE"))
        .andExpect(
            jsonPath("$.items[5].failedConditions[0]").value("혼인 7년 이내 신혼부부(또는 3개월 안 결혼 예정)여야 해요"))
        .andExpect(jsonPath("$.items[5].missingInputs", empty()))
        .andExpect(jsonPath("$.items[?(@.productCode == 'DIDIMDOL')].status").value("INELIGIBLE"))
        .andExpect(
            jsonPath("$.items[?(@.productCode == 'DIDIMDOL')].failedConditions[0]")
                .value("만 30세 미만 미혼 단독세대주는 받을 수 없어요"));
  }

  @Test
  void missingInputsTellWhatToAsk() throws Exception {
    call("{\"birthDate\": \"1999-05-05\"}")
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.counts.eligible").value(0))
        .andExpect(
            jsonPath("$.items[?(@.productCode == 'BEOTIMMOK_YOUTH')].missingInputs[*].field")
                .value(hasItem("loan.annualIncomeWon")))
        .andExpect(
            jsonPath("$.items[?(@.productCode == 'BEOTIMMOK_YOUTH')].missingInputs[*].label")
                .value(hasItem("부부합산 순자산")))
        .andExpect(
            jsonPath("$.items[?(@.productCode == 'DIDIMDOL_NEWLYWED')].missingInputs[*].field")
                .value(hasItem("loan.firstHomePurchase")));
  }

  @Test
  void profileAndDayAreOptional() throws Exception {
    mvc.perform(post(PATH).contentType(MediaType.APPLICATION_JSON).content("{}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.asOf").exists())
        .andExpect(jsonPath("$.items", hasSize(10)))
        .andExpect(jsonPath("$.items[*].status", not(hasItem("ELIGIBLE"))));
  }

  @Test
  void rejectsBrokenMoneyWithoutEchoingIt() throws Exception {
    call("{\"loan\": {\"annualIncomeWon\": -7654321}}")
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.detail").value(startsWith("profile.loan.annualIncomeWon")))
        .andExpect(content().string(not(containsString("7654321"))));
    call("{\"loan\": {\"annualIncomeWon\": 30000000, \"applicantAnnualIncomeWon\": 40000000}}")
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.detail").value(startsWith("profile.loan.applicantAnnualIncomeWon")));
  }

  @Test
  void personalInputsNeverReachTheLogs(CapturedOutput output) throws Exception {
    String profile =
        """
        {"birthDate": "1987-06-05", "household": {"homeless": true},
         "loan": {"annualIncomeWon": 43218765, "netAssetWon": 198765432}}""";
    call(profile)
        .andExpect(status().isOk())
        .andExpect(content().string(not(containsString("43218765"))))
        .andExpect(content().string(not(containsString("198765432"))));
    call(profile.replace("43218765", "-43218765")).andExpect(status().isBadRequest());
    assertThat(output.getAll())
        .doesNotContain("43218765")
        .doesNotContain("4,321")
        .doesNotContain("198765432")
        .doesNotContain("1987-06-05");
  }
}
