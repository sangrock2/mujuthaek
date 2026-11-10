package kr.mujuthaek.api.eligibility.rule;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.time.YearMonth;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class PeriodsTest {

  @ParameterizedTest
  @CsvSource({
    "1997-03-15, 2026-03-14, 28", // 생일 전날
    "1997-03-15, 2026-03-15, 29", // 생일
    "1986-10-17, 2026-10-16, 39", // 서리풀 공고: 1986.10.17 출생은 기준일 2026-10-16에 만 39세
    "2007-10-16, 2026-10-16, 19",
    "2004-02-29, 2026-02-28, 21", // 윤일생은 평년 2월 28일에는 아직
    "2004-02-29, 2026-03-01, 22",
  })
  void age(LocalDate birth, LocalDate reference, int expected) {
    assertThat(Periods.age(birth, reference)).isEqualTo(expected);
  }

  @Test
  void monthsAndYearsFromYearMonth() {
    LocalDate reference = LocalDate.of(2026, 10, 22);
    assertThat(Periods.fullMonths(YearMonth.of(2024, 3), reference)).isEqualTo(31);
    assertThat(Periods.fullMonths(YearMonth.of(2026, 10), reference)).isZero();
    assertThat(Periods.fullMonths(YearMonth.of(2027, 1), reference)).isZero(); // 미래
    assertThat(Periods.fullYears(YearMonth.of(2019, 10), reference)).isEqualTo(7);
    assertThat(Periods.fullYears(YearMonth.of(2019, 11), reference)).isEqualTo(6);
  }
}
