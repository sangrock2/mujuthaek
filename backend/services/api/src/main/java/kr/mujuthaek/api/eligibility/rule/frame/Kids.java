package kr.mujuthaek.api.eligibility.rule.frame;

import java.time.LocalDate;
import java.util.List;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.CountRule;

/** 자녀 세기. 미성년은 만 19세 미만이에요 (민법). 태아는 0세 자녀로 세요. */
final class Kids {

  static final int ADULT_AGE = 19;

  private Kids() {}

  /** 그날의 미성년 자녀 수 (unborn이면 태아 1명 더함). */
  static int minors(List<LocalDate> births, LocalDate day, boolean unborn) {
    long count =
        births.stream()
            .filter(b -> !b.isAfter(day))
            .filter(b -> Ages.on(b, day) < ADULT_AGE)
            .count();
    return (int) count + (unborn ? 1 : 0);
  }

  /** since 이후 출생(태아 포함) 자녀를 세는 방법에 따라 센 수. */
  static int newborns(
      List<LocalDate> births, LocalDate day, LocalDate since, CountRule rule, boolean unborn) {
    long bornSince =
        births.stream().filter(b -> !b.isBefore(since)).filter(b -> !b.isAfter(day)).count();
    int sinceCount = (int) bornSince + (unborn ? 1 : 0);
    return switch (rule) {
      case BORN_SINCE_ONLY -> sinceCount;
      case MINORS_IF_ANY_SINCE -> sinceCount > 0 ? minors(births, day, unborn) : 0;
    };
  }

  /** 막내 나이 (태아면 0세). 그날까지 태어난 자녀도 태아도 없으면 null. */
  static Integer youngestAge(List<LocalDate> births, LocalDate day, boolean unborn) {
    if (unborn) {
      return 0;
    }
    return births.stream()
        .filter(b -> !b.isAfter(day))
        .map(b -> Ages.on(b, day))
        .min(Integer::compare)
        .orElse(null);
  }
}
