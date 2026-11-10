package kr.mujuthaek.api.eligibility.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import kr.mujuthaek.api.common.exception.CustomException;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

/** 관리자 기준값 입력의 모양 검사. */
class AdminCriteriaServiceTest {

  private final JsonMapper json = JsonMapper.builder().build();

  @Test
  void incomeNeedsPositiveWonFromOnePersonHousehold() {
    assertThatCode(
            () ->
                AdminCriteriaService.checkData(
                    "MEDIAN_INCOME",
                    json.readTree("{\"monthlyWon\":{\"1\":2564238,\"2\":4199292}}")))
        .doesNotThrowAnyException();
    for (String bad :
        new String[] {
          "{}",
          "{\"monthlyWon\":{}}",
          "{\"monthlyWon\":{\"2\":4199292}}",
          "{\"monthlyWon\":{\"1\":0}}",
          "{\"monthlyWon\":{\"1\":\"2564238\"}}",
          "{\"monthlyWon\":{\"1\":2564238.5}}",
          "{\"monthlyWon\":{\"1\":2564238,\"x\":1}}",
          "[1]"
        }) {
      assertThatThrownBy(
              () -> AdminCriteriaService.checkData("URBAN_WORKER_INCOME", json.readTree(bad)))
          .as(bad)
          .isInstanceOf(CustomException.class);
    }
  }

  @Test
  void validFromMustBeInsideTheYear() {
    AdminCriteriaService.checkValidFrom(2026, java.time.LocalDate.of(2026, 2, 26));
    assertThatThrownBy(
            () -> AdminCriteriaService.checkValidFrom(2027, java.time.LocalDate.of(2026, 12, 1)))
        .isInstanceOf(CustomException.class);
  }

  @Test
  void rankCriteriaNeedsRanksOrByNoticeType() {
    assertThatCode(
            () -> AdminCriteriaService.checkData("RANK_CRITERIA", json.readTree("{\"ranks\":[]}")))
        .doesNotThrowAnyException();
    assertThatCode(
            () ->
                AdminCriteriaService.checkData(
                    "RANK_CRITERIA", json.readTree("{\"byNoticeType\":{}}")))
        .doesNotThrowAnyException();
    assertThatThrownBy(
            () -> AdminCriteriaService.checkData("RANK_CRITERIA", json.readTree("{\"x\":1}")))
        .isInstanceOf(CustomException.class);
  }

  @Test
  void usageFindsTheStandardOrRankAnywhereInTheFrame() {
    var median =
        json.readTree(
            "{\"groups\":[{\"id\":\"g\",\"rank\":null,\"criteria\":[{\"type\":\"INCOME\","
                + "\"standard\":\"MEDIAN_INCOME\",\"percent\":150}]}]}");
    var urbanAverage =
        json.readTree(
            "{\"groups\":[{\"id\":\"g\",\"rank\":1,\"criteria\":"
                + "[{\"standard\":\"URBAN_WORKER_AVERAGE_INCOME\"}]}]}");
    var none = json.readTree("{\"groups\":[{\"id\":\"g\",\"criteria\":[]}]}");
    assertThat(AdminCriteriaService.uses("MEDIAN_INCOME", median)).isTrue();
    assertThat(AdminCriteriaService.uses("MEDIAN_INCOME", urbanAverage)).isFalse();
    assertThat(AdminCriteriaService.uses("URBAN_WORKER_INCOME", urbanAverage)).isTrue();
    assertThat(AdminCriteriaService.uses("RANK_CRITERIA", urbanAverage)).isTrue();
    assertThat(AdminCriteriaService.uses("RANK_CRITERIA", median)).isFalse();
    assertThat(
            AdminCriteriaService.count(
                "MEDIAN_INCOME", java.util.stream.Stream.of(median, urbanAverage, none, null)))
        .isEqualTo(1);
  }
}
