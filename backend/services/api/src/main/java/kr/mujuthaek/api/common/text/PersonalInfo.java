package kr.mujuthaek.api.common.text;

import java.text.Normalizer;
import java.util.regex.Pattern;

/**
 * 공개 글(채팅, 신고·제보 설명)에 올리면 안 되는 개인정보: 휴대폰 번호와 주민등록번호(외국인등록번호 포함). 보내기 전에 막아서 DB에 남지 않게 해요.
 *
 * <p>다른 숫자를 잘못 막지 않게 좁게 잡아요: 휴대폰은 010·011·016~019로 시작하는 번호만(대표번호·지역번호는 막지 않음), 주민등록번호는 앞 6자리가 날짜
 * 모양(월 01~12, 일 01~31)이고 뒷자리 첫 숫자가 1~8일 때만.
 *
 * <p>검사 전에 글을 고르게 펴요. 전각 숫자(０１０), 다른 문자의 숫자, 폭 없는 공백(U+200B), NBSP, 긴 줄표(—), {@code +82} 국가번호,
 * {@code /}· {@code _} 구분자로 쓰면 예전 검사를 그냥 지나갔어요(2026-11-16 보안 감사 L-7). 저장하는 글은 바꾸지 않고, 검사용 사본만 펴요.
 */
public final class PersonalInfo {

  /** 숫자 묶음 사이에 올 수 있는 짧은 구분자 (펴고 난 뒤 기준) */
  private static final String SEP = "[ \\-./_()]{0,3}";

  private static final Pattern MOBILE =
      Pattern.compile(
          "(?<!\\d)(?:(?:\\+|00)82"
              + SEP
              + "0?|0)1[016789]"
              + SEP
              + "\\d{3,4}"
              + SEP
              + "\\d{4}(?!\\d)");

  private static final Pattern RESIDENT_NUMBER =
      Pattern.compile(
          "(?<!\\d)\\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\\d|3[01])" + SEP + "[1-8]\\d{6}(?!\\d)");

  private PersonalInfo() {}

  /** 휴대폰 번호나 주민등록번호처럼 보이는 글이 있으면 true. */
  public static boolean contains(String text) {
    if (text == null || text.isEmpty()) {
      return false;
    }
    String plain = normalize(text);
    return MOBILE.matcher(plain).find() || RESIDENT_NUMBER.matcher(plain).find();
  }

  /**
   * 검사용으로 펴요: NFKC(전각·원문자 → 보통 글자), 서식 문자(폭 없는 공백·소프트 하이픈 등) 지우기, 모든 문자의 십진 숫자 → 0~9,
   * 줄표·빼기표·「ㅡ」(NFKC 뒤 U+1173) → {@code -}, 모든 공백 → 띄어쓰기 한 칸.
   */
  static String normalize(String text) {
    String folded = Normalizer.normalize(text, Normalizer.Form.NFKC);
    StringBuilder out = new StringBuilder(folded.length());
    folded
        .codePoints()
        .forEach(
            cp -> {
              int type = Character.getType(cp);
              if (type == Character.FORMAT) {
                return;
              }
              if (Character.isDigit(cp)) {
                out.append((char) ('0' + Character.digit(cp, 10)));
              } else if (type == Character.DASH_PUNCTUATION
                  || cp == 0x2212
                  || cp == 0x3161
                  || cp == 0x1173) {
                out.append('-');
              } else if (Character.isWhitespace(cp) || Character.isSpaceChar(cp)) {
                out.append(' ');
              } else {
                out.appendCodePoint(cp);
              }
            });
    return out.toString();
  }
}
