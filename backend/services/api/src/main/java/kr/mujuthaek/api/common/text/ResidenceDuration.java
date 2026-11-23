package kr.mujuthaek.api.common.text;

import java.util.regex.Pattern;

/** A minimum residency period explicitly tied to residence or resident registration. */
public final class ResidenceDuration {
  private static final Pattern MINIMUM =
      Pattern.compile(
          "(?<![\\d.])(?:(?<years>[1-9]\\d{0,2})\\s*년(?:\\s*(?<extraMonths>\\d{1,2})\\s*개월)?|(?<months>[1-9]\\d{0,2})\\s*개월)"
              + "\\s*이상\\s*(?:(?:연속|계속)\\s*)?(?:거주|주민\\s*등록)");

  private ResidenceDuration() {}

  public static boolean agreesWithMinimum(String text, Integer months) {
    if (text == null) {
      return true;
    }
    var matches = MINIMUM.matcher(text);
    while (matches.find()) {
      String years = matches.group("years");
      String extraMonths = matches.group("extraMonths");
      int asserted =
          years == null
              ? Integer.parseInt(matches.group("months"))
              : Integer.parseInt(years) * 12
                  + (extraMonths == null ? 0 : Integer.parseInt(extraMonths));
      if (months == null || asserted != months) {
        return false;
      }
    }
    return true;
  }

  public static boolean hasExplicitMinimum(String text) {
    return text != null && MINIMUM.matcher(text).find();
  }
}
