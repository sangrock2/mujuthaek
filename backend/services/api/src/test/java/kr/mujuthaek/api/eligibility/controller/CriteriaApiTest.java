package kr.mujuthaek.api.eligibility.controller;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;
import kr.mujuthaek.api.TestDatabase;
import kr.mujuthaek.api.common.exception.GlobalExceptionHandlerAccess;
import kr.mujuthaek.api.eligibility.repository.CriteriaStore;
import kr.mujuthaek.api.eligibility.service.CriteriaService;
import kr.mujuthaek.api.notice.NoticeFixtures;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

/** 금액은 테스트용 값이에요 (실제 값은 그해 고시로 관리자가 넣어요). */
class CriteriaApiTest {

  private final JdbcTemplate jdbc = new JdbcTemplate(TestDatabase.dataSource());
  private final ZoneId seoul = ZoneId.of("Asia/Seoul");
  private final CriteriaService service =
      new CriteriaService(
          new CriteriaStore(jdbc),
          new kr.mujuthaek.api.eligibility.repository.LoanProductStore(jdbc),
          NoticeFixtures.JSON,
          Clock.fixed(LocalDate.of(2026, 10, 22).atStartOfDay(seoul).toInstant(), seoul));
  private final MockMvc mvc =
      MockMvcBuilders.standaloneSetup(
              new EligibilityController(
                  service,
                  org.mockito.Mockito.mock(
                      kr.mujuthaek.api.eligibility.service.SubscriptionScoreService.class),
                  org.mockito.Mockito.mock(
                      kr.mujuthaek.api.eligibility.service.NoticeEvaluationService.class),
                  org.mockito.Mockito.mock(
                      kr.mujuthaek.api.eligibility.service.PrepareCostService.class)))
          .setControllerAdvice(GlobalExceptionHandlerAccess.handler())
          .build();

  @BeforeEach
  void seed() {
    jdbc.update("delete from eligibility.criteria_sets");
    jdbc.update(
        "insert into eligibility.criteria_sets (kind, year, valid_from, data) values"
            + " ('MEDIAN_INCOME', 2026, '2026-01-01', '{\"monthlyWon\": {\"1\": 1000001, \"2\": 1600002}}'),"
            + " ('RANK_CRITERIA', 2026, '2026-01-01', '{\"ranks\": [{\"rank\": 2, \"rule\": \"ALL\","
            + " \"items\": [{\"key\": \"R2_ASSET\", \"label\": \"총자산가액 기준 이하\", \"limitWon\": 1}]}],"
            + " \"byNoticeType\": {\"HAPPY_HOUSING\": [{\"rank\": 1, \"rule\": \"ANY\", \"items\": []}]}}')");
  }

  @Test
  void criteriaForTheLatestYearInUse() throws Exception {
    mvc.perform(get("/api/v1/eligibility/criteria"))
        .andExpect(status().isOk())
        .andExpect(header().string("Cache-Control", "max-age=86400, public"))
        .andExpect(jsonPath("$.year").value(2026))
        .andExpect(jsonPath("$.validFrom").value("2026-01-01"))
        .andExpect(jsonPath("$.medianIncomeMonthlyWon.1").value(1000001))
        .andExpect(jsonPath("$.rankCriteria[0].items[0].key").value("R2_ASSET"));
  }

  @Test
  void noticeTypeSpecificRanks() throws Exception {
    mvc.perform(
            get("/api/v1/eligibility/criteria")
                .param("year", "2026")
                .param("noticeType", "HAPPY_HOUSING"))
        .andExpect(jsonPath("$.rankCriteria[0].rank").value(1));
  }

  @Test
  void yearWithoutCriteriaIsNotFound() throws Exception {
    mvc.perform(get("/api/v1/eligibility/criteria").param("year", "2019"))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("CRITERIA_NOT_FOUND"));
  }

  @Test
  void benchmarksForTheJudgeComeFromTheCriteriaTable() {
    var benchmarks = service.benchmarks();
    org.assertj.core.api.Assertions.assertThat(benchmarks.monthlyWon("MEDIAN_INCOME", 2026, 2))
        .isEqualTo(1600002L);
    org.assertj.core.api.Assertions.assertThat(benchmarks.monthlyWon("MEDIAN_INCOME", 2026, 7))
        .isNull();
    org.assertj.core.api.Assertions.assertThat(
            benchmarks.monthlyWon("URBAN_WORKER_INCOME", 2026, 1))
        .isNull();
  }

  @Test
  void monthlyIncomeForJudging() {
    org.assertj.core.api.Assertions.assertThat(service.monthlyIncome("MEDIAN_INCOME", 2026))
        .containsEntry("2", 1600002L);
    org.assertj.core.api.Assertions.assertThat(service.monthlyIncome("URBAN_WORKER_INCOME", 2026))
        .isEmpty();
  }

  @Test
  void incomeFallsBackToThePublishedBaseValues() {
    // criteria_sets에 없는 해(2025)는 고시 값 표(base_values)에서 읽어요
    org.assertj.core.api.Assertions.assertThat(service.monthlyIncome("MEDIAN_INCOME", 2025))
        .containsEntry("1", 2392013L);
    org.assertj.core.api.Assertions.assertThat(
            service.benchmarks().monthlyWon("MEDIAN_INCOME", 2025, 1))
        .isEqualTo(2392013L);
  }

  @Test
  void averageUrbanIncomeIsItsOwnTable() {
    var b = service.benchmarks();
    org.assertj.core.api.Assertions.assertThat(b.monthlyWon("URBAN_WORKER_INCOME", 2025, 1))
        .isEqualTo(3813363L);
    org.assertj.core.api.Assertions.assertThat(b.monthlyWon("URBAN_WORKER_AVERAGE_INCOME", 2025, 1))
        .isEqualTo(7533763L);
  }

  @Test
  void criteriaGiveTheCutsForAssetAndCarBands() throws Exception {
    mvc.perform(get("/api/v1/eligibility/criteria").param("year", "2026"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.assetCutsWon[0]").value(104000000)) // 2025 행복주택(대학생)
        .andExpect(jsonPath("$.assetCutsWon").value(org.hamcrest.Matchers.hasItem(251000000)))
        .andExpect(jsonPath("$.carCutsWon").value(org.hamcrest.Matchers.hasItem(45420000)));
  }

  @Test
  void urbanWorkerIncomeFallsBackToTheLatestEarlierYear() throws Exception {
    // 고시 값 표의 도시근로자 소득은 2025년까지 → 2026년 기준값에는 2025년 값과 연도를 줘요
    mvc.perform(get("/api/v1/eligibility/criteria").param("year", "2026"))
        .andExpect(jsonPath("$.urbanWorkerIncomeYear").value(2025))
        // 가구원수별 표 (가구당 평균 표 7,533,763원과 섞이지 않아요)
        .andExpect(jsonPath("$.urbanWorkerIncomeMonthlyWon.1").value(3813363));
  }

  @Test
  void withoutAdminCriteriaTheLatestPublishedYearIsUsed() throws Exception {
    jdbc.update("delete from eligibility.criteria_sets");
    mvc.perform(get("/api/v1/eligibility/criteria"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.year").value(2026))
        .andExpect(jsonPath("$.validFrom").value("2026-01-01"))
        .andExpect(jsonPath("$.medianIncomeMonthlyWon.1").exists())
        .andExpect(jsonPath("$.rankCriteria").doesNotExist());
  }
}
