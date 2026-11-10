package kr.mujuthaek.api.notice.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import org.junit.jupiter.api.Test;

/** 일정의 「진행 중」(current): 오늘이 일정 안인지. */
class NoticeDetailMapperCurrentTest {

  private static final LocalDate TODAY = LocalDate.of(2026, 11, 11);

  @Test
  void aPeriodIsCurrentFromItsFirstToItsLastDay() {
    assertThat(NoticeDetailMapper.within(TODAY, "2026-11-05", "2026-11-13")).isTrue();
    assertThat(NoticeDetailMapper.within(TODAY, "2026-11-11T10:00:00+09:00", "2026-11-11"))
        .isTrue();
    assertThat(NoticeDetailMapper.within(TODAY, "2026-11-12", "2026-11-20")).isFalse();
    assertThat(NoticeDetailMapper.within(TODAY, "2026-11-01", "2026-11-10")).isFalse();
  }

  @Test
  void aScheduleWithOneDateIsCurrentOnlyOnThatDay() {
    // 2026-11-11: 「12/2 당첨자 발표」(끝 날짜만)가 그날 전 내내 진행 중으로 보였음
    assertThat(NoticeDetailMapper.within(TODAY, null, "2026-12-02")).isFalse();
    assertThat(NoticeDetailMapper.within(TODAY, null, "2026-11-11")).isTrue();
    assertThat(NoticeDetailMapper.within(TODAY, "2026-11-01", null)).isFalse();
    assertThat(NoticeDetailMapper.within(TODAY, "2026-11-11", null)).isTrue();
    assertThat(NoticeDetailMapper.within(TODAY, null, null)).isFalse();
  }
}
