package kr.mujuthaek.api.eligibility.rule.frame;

import java.time.LocalDate;
import java.time.Period;

/** 만 나이: 그날까지 생일이 지났는지까지 본 나이. */
final class Ages {

  private Ages() {}

  static int on(LocalDate birthDate, LocalDate day) {
    return Period.between(birthDate, day).getYears();
  }
}
