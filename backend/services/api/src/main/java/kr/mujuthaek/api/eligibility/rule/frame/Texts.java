package kr.mujuthaek.api.eligibility.rule.frame;

import java.math.BigDecimal;
import java.util.List;
import java.util.stream.Collectors;

/** 판정 결과에 쓰는 문구. 기준만 쓰고 사용자가 넣은 값은 쓰지 않아요. */
final class Texts {

  private Texts() {}

  static String won(long amount) {
    return String.format("%,d원", amount);
  }

  static String percent(BigDecimal value) {
    return value.stripTrailingZeros().toPlainString() + "%";
  }

  static String ageRange(Integer min, Integer max) {
    if (min != null && max != null) {
      return "만 " + min + "~" + max + "세";
    }
    return min != null ? "만 " + min + "세 이상" : "만 " + max + "세 이하";
  }

  static String codes(List<String> codes) {
    return String.join(", ", codes);
  }

  static String labels(List<String> codes) {
    return codes.stream().map(Codes::label).collect(Collectors.joining(" · "));
  }
}
