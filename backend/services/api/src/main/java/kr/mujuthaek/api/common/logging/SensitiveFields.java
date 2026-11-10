package kr.mujuthaek.api.common.logging;

import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 저장하거나 로그에 남기면 안 되는 판정 입력 칸 (소득·자산·자동차가액·매출·가용 현금·수급 여부·순위 체크·생년월일, 그 구간 값).
 *
 * <p>요청 본문은 로그에 남기지 않지만, 예외 메시지나 객체의 toString에 값이 섞여 들어갈 수 있어서 남기기 전에 {@link #mask}로 가려요. 칸을 더하면
 * 여기에 이름을 넣어요.
 */
public final class SensitiveFields {

  public static final List<String> NAMES =
      List.of(
          "personalIncomeAnnualWon",
          "householdIncomeAnnualWon",
          "totalAssetsWon",
          "carValueWon",
          "availableCashWon",
          "annualRevenueWon",
          "welfareStatuses",
          "rankChecks",
          "birthDate",
          // 판정 입력의 구간 값 (2026-10-26): 구간도 남기지 않아요
          "birthMonth",
          "personalIncome",
          "householdIncome",
          "income",
          "assets",
          "car");

  public static final String MASK = "***";

  private static final String NAME_GROUP = "(" + String.join("|", NAMES) + ")";
  // JSON "칸": 또는 record·toString 칸= 다음의 값을 가려요. 값은 글자·숫자·배열·객체(겹쳐도 돼요)
  private static final Pattern JSON = Pattern.compile("\"" + NAME_GROUP + "\"\\s*:\\s*");
  private static final Pattern ASSIGNMENT = Pattern.compile("\\b" + NAME_GROUP + "=");

  private SensitiveFields() {}

  /** 민감한 칸의 값을 ***로 바꾼 글자. null이면 null. */
  public static String mask(String text) {
    if (text == null) {
      return null;
    }
    String masked = replace(JSON, text, "\"" + MASK + "\"", true);
    return replace(ASSIGNMENT, masked, MASK, false);
  }

  private static String replace(Pattern pattern, String text, String replacement, boolean json) {
    Matcher m = pattern.matcher(text);
    StringBuilder out = new StringBuilder();
    int from = 0;
    while (m.find(from)) {
      out.append(text, from, m.end()).append(replacement);
      from = valueEnd(text, m.end(), json);
    }
    return out.append(text.substring(from)).toString();
  }

  /**
   * 값이 끝나는 위치. 괄호([{ ( 와 짝)는 깊이를 세고, JSON 글자("…")는 안의 쉼표·괄호를 건너뛰어요. 깊이 0에서 , ) ] } 또는 (JSON이면) 공백을
   * 만나면 끝이에요.
   */
  private static int valueEnd(String text, int start, boolean json) {
    int depth = 0;
    int i = start;
    while (i < text.length()) {
      char c = text.charAt(i);
      if (json && c == '"') {
        i++;
        while (i < text.length() && text.charAt(i) != '"') {
          i += text.charAt(i) == '\\' ? 2 : 1;
        }
        i++;
        if (depth == 0) {
          return Math.min(i, text.length());
        }
        continue;
      }
      if (c == '[' || c == '{' || c == '(') {
        depth++;
      } else if (c == ']' || c == '}' || c == ')') {
        if (depth == 0) {
          return i;
        }
        depth--;
        if (depth == 0 && json) {
          return i + 1;
        }
      } else if (depth == 0 && (c == ',' || (json && Character.isWhitespace(c)))) {
        return i;
      }
      i++;
    }
    return i;
  }

  /** 예외를 로그에 남기기 전에: 메시지(원인 포함)를 가린 같은 모양의 예외. 스택 위치는 그대로예요. */
  public static Throwable masked(Throwable t) {
    Throwable cause = t.getCause() != null && t.getCause() != t ? masked(t.getCause()) : null;
    var copy = new MaskedException(t.getClass().getName() + ": " + mask(t.getMessage()), cause);
    copy.setStackTrace(t.getStackTrace());
    return copy;
  }

  /** 가린 메시지를 담는 예외. 원래 예외 이름은 메시지 앞에 있어요. */
  static final class MaskedException extends RuntimeException {
    MaskedException(String message, Throwable cause) {
      super(message, cause, false, true);
    }

    @Override
    public String toString() {
      return getMessage();
    }
  }
}
