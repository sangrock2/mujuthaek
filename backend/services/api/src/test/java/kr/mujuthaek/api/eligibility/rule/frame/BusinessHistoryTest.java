package kr.mujuthaek.api.eligibility.rule.frame;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.util.List;
import kr.mujuthaek.api.eligibility.rule.frame.Applicant.BusinessRecord;
import org.junit.jupiter.api.Test;

/** 사업 이력 계산: 영업 중 여부, 겹치는 기간은 한 번만 센 영업 경력, 폐업 기간. */
class BusinessHistoryTest {

  private static final LocalDate DAY = LocalDate.of(2026, 10, 12);

  private static BusinessRecord business(String opened, String closed) {
    return new BusinessRecord(
        LocalDate.parse(opened), closed == null ? null : LocalDate.parse(closed));
  }

  @Test
  void aBusinessClosingOnTheDayIsNoLongerOperating() {
    assertThat(BusinessHistory.operating(List.of(business("2020-01-01", "2026-10-12")), DAY))
        .isEmpty();
    assertThat(BusinessHistory.operating(List.of(business("2020-01-01", "2026-10-13")), DAY))
        .hasSize(1);
    assertThat(BusinessHistory.operating(List.of(business("2026-10-13", null)), DAY))
        .as("기준일 뒤 개업")
        .isEmpty();
  }

  @Test
  void careerCountsOverlappingYearsOnce() {
    // 2018-01-01 ~ 2022-01-01 (48개월)과 2020-01-01 ~ 2023-01-01 (겹침 포함 합치면 60개월)
    List<BusinessRecord> history =
        List.of(business("2018-01-01", "2022-01-01"), business("2020-01-01", "2023-01-01"));
    assertThat(BusinessHistory.careerMonths(history, DAY, null)).isEqualTo(60);
  }

  @Test
  void careerOnlyCountsTheRecentWindow() {
    // 최근 10년(2016-10-12 ~)으로 자르면 2016-10-12 ~ 2023-06-30 = 80개월 (남는 18일은 버려요)
    List<BusinessRecord> history = List.of(business("2015-03-02", "2023-06-30"));
    assertThat(BusinessHistory.careerMonths(history, DAY, 10)).isEqualTo(80);
  }

  @Test
  void closuresAreMatchedInclusively() {
    List<BusinessRecord> history = List.of(business("2020-01-01", "2026-01-28"));
    assertThat(
            BusinessHistory.closedBetween(
                history, LocalDate.of(2026, 1, 28), LocalDate.of(2026, 2, 27)))
        .isTrue();
    assertThat(
            BusinessHistory.closedBetween(
                history, LocalDate.of(2026, 1, 29), LocalDate.of(2026, 2, 27)))
        .isFalse();
  }
}
