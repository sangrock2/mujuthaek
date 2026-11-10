package kr.mujuthaek.api.eligibility.rule;

import java.time.LocalDate;
import java.time.Period;
import java.time.YearMonth;
import java.time.temporal.ChronoUnit;

/**
 * 판정에 쓰는 나이·기간 계산. 기준일은 공고마다 달라요(공고일·신청일 등, 판정 틀의 referenceDate).
 *
 * <p>연월만 아는 값(혼인신고·무주택 시작·청약통장 가입)은 그 달 어느 날인지 몰라요. 그 달 1일로 보면 기간이 가장 길고({@link #fullMonths}), 말일로
 * 보면 가장 짧아요({@link #shortestFullMonths}). 쓰는 곳이 어느 쪽이 안전한지 골라요: 기간이 길수록 유리한 가점은 짧은 쪽으로(점수를 부풀리지
 * 않게), 「N년 이내」 자격은 두 쪽을 다 보고 갈리면 확인 필요로. (2026-11-11: 예전 설명은 1일로 보면 「실제보다 길게 나오지 않는다」고 했지만 반대였어요.
 * 1일은 실제 날짜보다 앞이라 기간이 0~30일 길게 나와요)
 */
public final class Periods {

  private Periods() {}

  /** 만 나이: 생일이 지나야 한 살 더해요. 2월 29일생은 평년에 3월 1일에 나이가 늘어요. */
  public static int age(LocalDate birthDate, LocalDate referenceDate) {
    return Period.between(birthDate, referenceDate).getYears();
  }

  /** from을 그 달 1일로 보고 기준일까지 꽉 찬 개월 수(가장 긴 경우). 기준일이 앞이면 0. */
  public static int fullMonths(YearMonth from, LocalDate referenceDate) {
    return monthsBetween(from.atDay(1), referenceDate);
  }

  /** from을 그 달 말일로 보고 기준일까지 꽉 찬 개월 수(가장 짧은 경우). 기준일이 앞이면 0. */
  public static int shortestFullMonths(YearMonth from, LocalDate referenceDate) {
    return monthsBetween(from.atEndOfMonth(), referenceDate);
  }

  /** from을 그 달 1일로 보고 기준일까지 꽉 찬 년 수(가장 긴 경우). */
  public static int fullYears(YearMonth from, LocalDate referenceDate) {
    return fullMonths(from, referenceDate) / 12;
  }

  private static int monthsBetween(LocalDate start, LocalDate referenceDate) {
    if (referenceDate.isBefore(start)) {
      return 0;
    }
    return (int) ChronoUnit.MONTHS.between(start, referenceDate);
  }
}
