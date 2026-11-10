package kr.mujuthaek.api.notice.domain;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 같은 공고로 보이는지 (2-13). 스프링·DB 없이 값만 보고 정해요. 같다고 보면 자동으로 합쳐요(2026-10-21 결정). 잘못 합치지 않도록 아래를 모두 만족할 때만
 * 같다고 봐요.
 *
 * <ul>
 *   <li>공급 기관이 같아요 (정식 명칭·약칭은 같은 기관으로 봐요: 한국토지주택공사 = LH).
 *   <li>공고일 차이가 {@link #WINDOW_DAYS}일 이내예요 (둘 다 알아야 해요). 같은 공고가 기관 게시판과 LH API에 다른 날 올라오거나, 늦게 올라온
 *       정정본이 따로 들어오는 경우가 있어 넉넉히 봐요. 수집기가 정정공고로 연결해 준 글은 이 판별을 거치지 않고 원래 공고의 새 버전이 돼요.
 *   <li>제목이 같거나(띄어쓰기·기호·대소문자 무시) 단지·건물 이름이 하나 이상 같아요(한쪽이 다른 쪽을 포함해도 같음). 출처마다 제목 형식이 달라도 단지 이름으로
 *       잡아요.
 *   <li>모집 회차 표시(「2차」, 추가·잔여·예비·재공고·수시)가 같아요. 같은 단지라도 회차가 다르면 다른 공고예요.
 *   <li>공급 유형이 둘 다 있으면 같아요.
 *   <li>지역(시군구)이 겹쳐요. 둘 다 지역을 모르면 지역 조건은 보지 않아요.
 * </ul>
 */
public final class DuplicateRule {

  /** 같은 공고로 볼 공고일 차이 (사용자 결정 2026-10-21: 한 달). */
  public static final int WINDOW_DAYS = 30;

  /** 같은 공고로 본 근거 코드. */
  public static final String REASON = "SAME_PUBLISHER_NAME_ROUND_REGION_WITHIN_30_DAYS";

  private static final Pattern ROUND = Pattern.compile("(\\d+)\\s*차|추가|잔여|예비|재공고|수시|재모집");

  private DuplicateRule() {}

  /**
   * 비교에 쓰는 공고 정보.
   *
   * @param complexNames 위치의 단지·건물 이름 (없으면 빈 집합)
   * @param supplyType 공급 유형 (모르면 null)
   */
  public record Identity(
      String publisher,
      LocalDate announcedOn,
      String title,
      Set<String> sigunguCodes,
      Set<String> complexNames,
      String supplyType) {

    public Identity(
        String publisher, LocalDate announcedOn, String title, Set<String> sigunguCodes) {
      this(publisher, announcedOn, title, sigunguCodes, Set.of(), null);
    }
  }

  public static boolean likelySame(Identity a, Identity b) {
    if (a.publisher() == null || a.announcedOn() == null || b.announcedOn() == null) {
      return false;
    }
    if (!publisher(a.publisher()).equals(publisher(b.publisher()))
        || Math.abs(ChronoUnit.DAYS.between(a.announcedOn(), b.announcedOn())) > WINDOW_DAYS) {
      return false;
    }
    boolean sameTitle = normalize(a.title()).equals(normalize(b.title()));
    if (!sameTitle && !sameComplex(names(a.complexNames()), names(b.complexNames()))) {
      return false;
    }
    if (!rounds(a.title()).equals(rounds(b.title()))) {
      return false;
    }
    if (a.supplyType() != null
        && b.supplyType() != null
        && !normalize(a.supplyType()).equals(normalize(b.supplyType()))) {
      return false;
    }
    Set<String> left = a.sigunguCodes();
    Set<String> right = b.sigunguCodes();
    if (left.isEmpty() && right.isEmpty()) {
      return true;
    }
    return !Collections.disjoint(left, right);
  }

  /** 공급 기관 정식 명칭·약칭 (출처마다 표기가 달라요. 실측 2026-10-21: 「LH 경남지역본부」·「한국토지주택공사 경남지역본부」). */
  private static final java.util.Map<String, String> PUBLISHER_ALIASES =
      java.util.Map.of(
          "한국토지주택공사", "lh",
          "토지주택공사", "lh",
          "서울주택도시공사", "sh",
          "경기주택도시공사", "gh");

  /**
   * 공급 기관을 비교용으로: 띄어쓰기·기호를 빼고 정식 명칭을 약칭으로 바꿔요. LH 지역본부는 「LH」를 붙이지 않고 쓰기도 해서(「광주전남지역본부」) 지역본부 앞의 기관
   * 약칭은 뺍니다.
   */
  public static String publisher(String text) {
    String p = normalize(text);
    // 긴 이름부터 바꿔요(「한국토지주택공사」를 「토지주택공사」보다 먼저)
    List<String> names =
        PUBLISHER_ALIASES.keySet().stream()
            .sorted(java.util.Comparator.comparingInt(String::length).reversed())
            .toList();
    for (String name : names) {
      p = p.replace(name, PUBLISHER_ALIASES.get(name));
    }
    for (String prefix : List.of("lh", "sh", "gh")) {
      if (p.startsWith(prefix) && p.length() > prefix.length() && p.endsWith("본부")) {
        return p.substring(prefix.length());
      }
    }
    return p;
  }

  /** 단지 이름이 같거나 한쪽이 다른 쪽을 포함하는지(「빛가람LH3단지」 ⊂ 「광주전남혁신 빛가람LH3단지」). 짧은 이름(4글자 미만)은 같을 때만. */
  private static boolean sameComplex(Set<String> left, Set<String> right) {
    for (String a : left) {
      for (String b : right) {
        if (a.equals(b)
            || (Math.min(a.length(), b.length()) >= 4 && (a.contains(b) || b.contains(a)))) {
          return true;
        }
      }
    }
    return false;
  }

  /** 단지·건물 이름을 비교용으로(빈 이름은 뺌). */
  private static Set<String> names(Set<String> names) {
    Set<String> out = new TreeSet<>();
    for (String name : names) {
      String n = normalize(name);
      if (n.length() >= 2) {
        out.add(n);
      }
    }
    return out;
  }

  /** 제목의 모집 회차 표시 (「2차」 → 2차, 추가·잔여·예비·재공고·수시·재모집). */
  static Set<String> rounds(String title) {
    Set<String> out = new TreeSet<>();
    if (title == null) {
      return out;
    }
    Matcher m = ROUND.matcher(title);
    while (m.find()) {
      out.add(m.group(1) != null ? m.group(1) + "차" : m.group());
    }
    return out;
  }

  /** 글자와 숫자만 남기고 소문자로 (띄어쓰기·괄호·기호 차이는 같은 제목으로 봐요). */
  public static String normalize(String text) {
    if (text == null) {
      return "";
    }
    StringBuilder out = new StringBuilder();
    text.codePoints()
        .filter(Character::isLetterOrDigit)
        .forEach(c -> out.appendCodePoint(Character.toLowerCase(c)));
    return out.toString().toLowerCase(Locale.ROOT);
  }
}
