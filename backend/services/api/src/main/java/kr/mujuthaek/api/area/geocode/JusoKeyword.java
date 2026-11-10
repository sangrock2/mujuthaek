package kr.mujuthaek.api.area.geocode;

import java.util.regex.Pattern;

/**
 * 검색 API에 보낼 검색어 거르기. 공식 안내의 제한: 특수문자 {@code % = > < [ ]}와 SQL 예약어(OR, SELECT, INSERT, DELETE,
 * UPDATE, CREATE, DROP, EXEC, UNION, FETCH, DECLARE, TRUNCATE)는 쓸 수 없어요(E0013).
 *
 * <p>예약어는 낱말 하나일 때만 지워요(공식 예제처럼 글자 일부까지 지우면 "TOWER" 같은 건물명이 망가져요). 공백은 하나로 줄여요.
 */
final class JusoKeyword {

  private static final Pattern SPECIAL = Pattern.compile("[%=><\\[\\]]");
  private static final Pattern RESERVED =
      Pattern.compile(
          "\\b(OR|SELECT|INSERT|DELETE|UPDATE|CREATE|DROP|EXEC|UNION|FETCH|DECLARE|TRUNCATE)\\b",
          Pattern.CASE_INSENSITIVE);
  private static final Pattern SPACES = Pattern.compile("\\s+");

  private JusoKeyword() {}

  static String clean(String keyword) {
    if (keyword == null) {
      return "";
    }
    String s = SPECIAL.matcher(keyword).replaceAll(" ");
    s = RESERVED.matcher(s).replaceAll(" ");
    return SPACES.matcher(s).replaceAll(" ").trim();
  }
}
