package kr.mujuthaek.api.eligibility.rule;

import java.time.LocalDate;
import java.time.Period;
import java.time.YearMonth;
import java.time.temporal.ChronoUnit;

/**
 * 판정에 쓰는 나이·기간 계산. 기준일은 공고마다 달라요(공고일·신청일 등, 판정 틀의 referenceDate).
 *
 * <p>연월만 아는 값(혼인신고·무주택 시작·청약통장 가입)은 그 달 1일로 봐요. 그래서 기간은 실제보다 길게 나오지 않아요(0~30일 짧을 수 있음).
 */
public final class Periods {

  private Periods() {}

  /** 만 나이: 생일이 지나야 한 살 더해요. 2월 29일생은 평년에 3월 1일에 나이가 늘어요. */
  public static int age(LocalDate birthDate, LocalDate referenceDate) {
    return Period.between(birthDate, referenceDate).getYears();
  }

  /** from(그 달 1일)부터 기준일까지 꽉 찬 개월 수. 기준일이 앞이면 0. */
  public static int fullMonths(YearMonth from, LocalDate referenceDate) {
    LocalDate start = from.atDay(1);
    if (referenceDate.isBefore(start)) {
      return 0;
    }
    return (int) ChronoUnit.MONTHS.between(start, referenceDate);
  }

  /** from(그 달 1일)부터 기준일까지 꽉 찬 년 수. */
  public static int fullYears(YearMonth from, LocalDate referenceDate) {
    return fullMonths(from, referenceDate) / 12;
  }
}
