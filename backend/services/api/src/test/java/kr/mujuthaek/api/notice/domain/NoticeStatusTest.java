package kr.mujuthaek.api.notice.domain;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

/** D-day. 접수 상태 계산은 ApplicationStatusCalculatorTest에서 봐요. */
class NoticeStatusTest {

  private static final LocalDate TODAY = LocalDate.of(2026, 10, 22);

  @ParameterizedTest
  @CsvSource({
    "2026-10-31, 9",
    "2026-10-22, 0", // 마감일 당일
    "2026-10-21,", // 마감 지남
    ",", // 마감일 모름
  })
  void dday(LocalDate end, Integer dday) {
    assertThat(NoticeStatus.dday(end, TODAY)).isEqualTo(dday);
  }
}
