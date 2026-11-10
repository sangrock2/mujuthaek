package kr.mujuthaek.api.eligibility.rule.frame;

import java.time.LocalDate;
import java.time.Period;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import kr.mujuthaek.api.eligibility.rule.frame.Applicant.BusinessRecord;

/** 사업 이력(개업일·폐업일)으로 영업 중 여부, 영업 경력, 폐업 이력을 계산해요. */
final class BusinessHistory {

  private BusinessHistory() {}

  /** 그날 영업 중인 사업: 개업일이 그날 이전(같은 날 포함)이고, 폐업일이 없거나 그날보다 뒤. */
  static List<BusinessRecord> operating(List<BusinessRecord> history, LocalDate day) {
    return history.stream()
        .filter(b -> !b.openedOn().isAfter(day))
        .filter(b -> b.closedOn() == null || b.closedOn().isAfter(day))
        .toList();
  }

  /**
   * 영업 경력 개월 수. 영업 기간(개업일~폐업일, 영업 중이면 그날)을 [그날 − withinYears년, 그날]로 자르고 겹치는 기간은 한 번만 세요. 개월은 달력
   * 기준이고 남는 날은 버려요.
   */
  static int careerMonths(List<BusinessRecord> history, LocalDate day, Integer withinYears) {
    LocalDate windowStart = withinYears == null ? LocalDate.MIN : day.minusYears(withinYears);
    List<LocalDate[]> spans = new ArrayList<>();
    for (BusinessRecord b : history) {
      LocalDate start = b.openedOn().isAfter(windowStart) ? b.openedOn() : windowStart;
      LocalDate end = b.closedOn() == null || b.closedOn().isAfter(day) ? day : b.closedOn();
      if (start.isBefore(end)) {
        spans.add(new LocalDate[] {start, end});
      }
    }
    spans.sort(Comparator.comparing(s -> s[0]));
    List<LocalDate[]> merged = new ArrayList<>();
    for (LocalDate[] span : spans) {
      LocalDate[] last = merged.isEmpty() ? null : merged.getLast();
      if (last != null && !span[0].isAfter(last[1])) {
        if (span[1].isAfter(last[1])) {
          last[1] = span[1];
        }
      } else {
        merged.add(new LocalDate[] {span[0], span[1]});
      }
    }
    long months = 0;
    for (LocalDate[] span : merged) {
      months += Period.between(span[0], span[1]).toTotalMonths();
    }
    return (int) months;
  }

  /** 폐업일이 from~to(둘 다 포함) 안인 사업이 있는지. */
  static boolean closedBetween(List<BusinessRecord> history, LocalDate from, LocalDate to) {
    return history.stream()
        .anyMatch(
            b -> b.closedOn() != null && !b.closedOn().isBefore(from) && !b.closedOn().isAfter(to));
  }
}
