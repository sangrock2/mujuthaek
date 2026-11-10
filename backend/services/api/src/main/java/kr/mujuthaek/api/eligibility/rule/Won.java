package kr.mujuthaek.api.eligibility.rule;

/** 화면 문구용 금액: 245000000 → "2억 4,500만 원", 45420000 → "4,542만 원", 2669354 → "266만 9,354원". */
final class Won {

  private Won() {}

  static String format(long won) {
    long eok = won / 100_000_000;
    long man = won % 100_000_000 / 10_000;
    long rest = won % 10_000;
    StringBuilder out = new StringBuilder();
    if (eok > 0) {
      out.append(String.format("%,d억", eok));
    }
    if (man > 0) {
      out.append(out.isEmpty() ? "" : " ").append(String.format("%,d만", man));
    }
    if (rest > 0) {
      out.append(out.isEmpty() ? "" : " ").append(String.format("%,d", rest));
    }
    if (out.isEmpty()) {
      return "0원";
    }
    return out + (rest > 0 ? "원" : " 원");
  }
}
