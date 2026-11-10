package kr.mujuthaek.api.area.geocode;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 공고에 적힌 주소 글자를 찾기 좋게 정리해요. 스프링·DB 없이 글자만 다뤄요.
 *
 * <ul>
 *   <li>괄호 안 설명을 떼요: {@code (5호선 길동역 1번 출구)}, {@code (미평동,미평주공아파트)}. 괄호 안의 첫 동·가·리 이름은 따로 남겨요
 *   <li>꼬리를 떼요: {@code 외 7필지}, {@code 일원}, {@code 일대}, {@code 번지}
 *   <li>시도 이름을 지금 이름으로 통일해요: {@code 서울시} → {@code 서울특별시}, {@code 광주광역시}·{@code 전라남도} → {@code
 *       전남광주통합특별시}
 *   <li>지번과 도로명이 한 줄에 같이 적혀 시도가 중간에 나오면 시도부터 써요: {@code 가장동 52-37 대전광역시 서구 유등로465번길 61}
 *   <li>도로명 안 띄어쓰기를 붙여요: {@code 남부순환로 180길} → {@code 남부순환로180길}, {@code 달오 2길} → {@code 달오2길}
 * </ul>
 */
public final class AddressNormalizer {

  /** 정리한 주소와, 괄호 안에서 찾은 동·가·리 이름(없으면 null). */
  public record Normalized(String text, String dongHint) {}

  /** 시도 이름 → 지금 정식 이름 (2026 개편 반영). 긴 이름부터 맞춰 봐요. */
  static final Map<String, String> SIDO = new LinkedHashMap<>();

  static {
    sido("서울특별시", "서울시", "서울");
    sido("부산광역시", "부산시", "부산");
    sido("대구광역시", "대구시", "대구");
    sido("인천광역시", "인천시", "인천");
    sido("대전광역시", "대전시", "대전");
    sido("울산광역시", "울산시", "울산");
    sido("세종특별자치시", "세종시", "세종");
    sido("경기도", "경기");
    sido("강원특별자치도", "강원도", "강원");
    sido("충청북도", "충북");
    sido("충청남도", "충남");
    sido("전북특별자치도", "전라북도", "전북");
    // "광주시"·"광주"는 경기도 광주시와 헷갈려서 별칭으로 두지 않아요.
    sido("전남광주통합특별시", "광주광역시", "전라남도", "전남");
    sido("경상북도", "경북");
    sido("경상남도", "경남");
    sido("제주특별자치도", "제주도", "제주");
  }

  private static void sido(String official, String... aliases) {
    SIDO.put(official, official);
    for (String alias : aliases) {
      SIDO.put(alias, official);
    }
  }

  private static final Pattern PAREN = Pattern.compile("\\(([^()]*)\\)");
  private static final Pattern DONG_IN_PAREN =
      Pattern.compile("^\\s*([가-힣0-9]+(?:동|가|리))(?:[,\\s]|$)");
  private static final Pattern TAIL =
      Pattern.compile("외\\s*\\d+\\s*필지|외(?=\\s|$|,)|일원|일대|번지(?=\\s|$|,|외|일)");
  // "남부순환로 180길", "달오 2길", "중앙로 12번길" → 붙여요. 뒤에 건물번호가 있을 때만(동 이름 등과 헷갈리지 않게).
  private static final Pattern ROAD_SPACE =
      Pattern.compile("([가-힣0-9]+(?:로|길)?)\\s+(\\d+(?:번?[가-힣]?)(?:로|길))(?=\\s*(?:지하\\s*)?\\d)");

  private AddressNormalizer() {}

  public static Normalized normalize(String raw) {
    if (raw == null) {
      return new Normalized("", null);
    }
    String text = raw.replace(' ', ' ').replace('　', ' ').strip();
    String dongHint = null;
    Matcher paren = PAREN.matcher(text);
    StringBuilder noParen = new StringBuilder();
    while (paren.find()) {
      Matcher dong = DONG_IN_PAREN.matcher(paren.group(1));
      if (dongHint == null && dong.find()) {
        dongHint = dong.group(1);
      }
      paren.appendReplacement(noParen, " ");
    }
    paren.appendTail(noParen);
    text = noParen.toString();
    text = text.replaceAll("[,·]", " ");
    text = fromSido(text);
    text = TAIL.matcher(text).replaceAll(" ");
    text = text.replaceAll("\\s+", " ").strip();
    text = ROAD_SPACE.matcher(text).replaceAll("$1$2");
    text = unifySido(text);
    return new Normalized(text, dongHint);
  }

  /** 시도 이름이 맨 앞이 아니라 중간에 나오면(앞에 지번이 따로 적힌 줄) 시도부터 써요. */
  private static String fromSido(String text) {
    String trimmed = text.strip();
    for (String name : SIDO.keySet()) {
      if (name.length() < 3) {
        continue;
      }
      if (trimmed.startsWith(name)) {
        return trimmed;
      }
    }
    for (String name : SIDO.keySet()) {
      if (name.length() < 3) {
        continue;
      }
      int at = trimmed.indexOf(" " + name + " ");
      if (at > 0) {
        return trimmed.substring(at + 1);
      }
    }
    return trimmed;
  }

  private static String unifySido(String text) {
    int space = text.indexOf(' ');
    String first = space < 0 ? text : text.substring(0, space);
    String official = SIDO.get(first);
    if (official == null || official.equals(first)) {
      return text;
    }
    return official + (space < 0 ? "" : text.substring(space));
  }
}
