package kr.mujuthaek.api.eligibility.rule.loan;

import java.util.ArrayList;
import java.util.List;

/** 금액을 읽기 쉬운 글자로: 345000000 → "3억 4,500만 원", 50000000 → "5,000만 원". */
final class Wons {

  private Wons() {}

  static String text(long won) {
    long eok = won / 100_000_000;
    long man = won % 100_000_000 / 10_000;
    long rest = won % 10_000;
    List<String> parts = new ArrayList<>();
    if (eok > 0) {
      parts.add(String.format("%,d억", eok));
    }
    if (man > 0) {
      parts.add(String.format("%,d만", man));
    }
    if (rest > 0 || parts.isEmpty()) {
      parts.add(String.format("%,d", rest));
    }
    return String.join(" ", parts) + " 원";
  }
}
