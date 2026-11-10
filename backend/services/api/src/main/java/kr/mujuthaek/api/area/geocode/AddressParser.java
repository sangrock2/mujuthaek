package kr.mujuthaek.api.area.geocode;

import java.util.regex.Matcher;
import java.util.regex.Pattern;
import kr.mujuthaek.api.area.geocode.ParsedAddress.Kind;

/**
 * 정리한 공고 주소에서 시도·시군구와 도로명·건물번호(또는 법정동·지번)를 나눠요. 스프링·DB 없이 글자만 다뤄요.
 *
 * <p>도로명과 지번이 둘 다 있으면 도로명을 써요(사전이 도로명 기준이라). 건물번호 뒤의 건물명·동·호는 읽지 않아요.
 */
public final class AddressParser {

  // 도로명 + 건물번호. 번호 바로 뒤가 글자면(예: 22번길, 1가) 아직 도로명이라 더 길게 맞춰요.
  private static final Pattern ROAD =
      Pattern.compile(
          "(?<![가-힣0-9])([가-힣0-9]+?(?:로|길))\\s*(지하\\s*)?(\\d+)(?:-(\\d+))?(?![0-9가-힣])");
  // 법정동·리 + 지번. 리는 앞의 읍면을 같이 써요.
  private static final Pattern JIBUN =
      Pattern.compile(
          "(?:([가-힣0-9]+(?:읍|면))\\s+)?(?<![가-힣0-9])([가-힣0-9]+(?:동|리|가))\\s*(산\\s*)?(\\d+)(?:-(\\d+))?(?![0-9])");
  private static final Pattern SIGUNGU = Pattern.compile("^[가-힣]+(?:시|군|구)$");

  private AddressParser() {}

  public static ParsedAddress parse(String raw) {
    AddressNormalizer.Normalized normalized = AddressNormalizer.normalize(raw);
    String text = normalized.text();
    String[] tokens = text.isEmpty() ? new String[0] : text.split(" ");

    int at = 0;
    String sido = null;
    if (tokens.length > 0 && AddressNormalizer.SIDO.containsValue(tokens[0])) {
      sido = tokens[0];
      at = 1;
    }
    String sigungu = null;
    if (at < tokens.length && SIGUNGU.matcher(tokens[at]).matches() && !isRoad(tokens[at])) {
      sigungu = tokens[at];
      at++;
      if (sigungu.endsWith("시")
          && at < tokens.length
          && tokens[at].endsWith("구")
          && SIGUNGU.matcher(tokens[at]).matches()) {
        sigungu = sigungu + " " + tokens[at];
        at++;
      }
    }
    String rest = String.join(" ", java.util.Arrays.copyOfRange(tokens, at, tokens.length));

    Matcher road = ROAD.matcher(rest);
    if (road.find()) {
      return new ParsedAddress(
          Kind.ROAD,
          sido,
          sigungu,
          road.group(1),
          road.group(2) != null,
          Integer.parseInt(road.group(3)),
          road.group(4) == null ? 0 : Integer.parseInt(road.group(4)),
          normalized.dongHint(),
          false,
          0,
          0,
          text);
    }
    Matcher jibun = JIBUN.matcher(rest);
    if (jibun.find()) {
      String dong = jibun.group(2);
      if (dong.endsWith("리") && jibun.group(1) != null) {
        dong = jibun.group(1) + " " + dong;
      }
      return new ParsedAddress(
          Kind.JIBUN,
          sido,
          sigungu,
          null,
          false,
          0,
          0,
          dong,
          jibun.group(3) != null,
          Integer.parseInt(jibun.group(4)),
          jibun.group(5) == null ? 0 : Integer.parseInt(jibun.group(5)),
          text);
    }
    Kind kind = sido != null || sigungu != null ? Kind.AREA_ONLY : Kind.UNKNOWN;
    return new ParsedAddress(
        kind, sido, sigungu, null, false, 0, 0, normalized.dongHint(), false, 0, 0, text);
  }

  private static boolean isRoad(String token) {
    return token.endsWith("로") || token.endsWith("길");
  }
}
