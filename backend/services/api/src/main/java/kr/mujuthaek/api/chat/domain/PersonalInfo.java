package kr.mujuthaek.api.chat.domain;

import java.util.regex.Pattern;

/**
 * 채팅에 올리면 안 되는 개인정보: 휴대폰 번호와 주민등록번호(외국인등록번호 포함). 보내기 전에 막아서 DB에 남지 않게 해요.
 *
 * <p>다른 숫자를 잘못 막지 않게 좁게 잡아요: 휴대폰은 010·011·016~019로 시작하는 번호만(대표번호·지역번호는 막지 않음), 주민등록번호는 앞 6자리가 날짜
 * 모양(월 01~12, 일 01~31)이고 뒷자리 첫 숫자가 1~8일 때만. 띄어쓰기·하이픈·점으로 나눠 써도 잡아요.
 */
public final class PersonalInfo {

  private static final Pattern MOBILE =
      Pattern.compile("(?<!\\d)01[016789][-.\\s]?\\d{3,4}[-.\\s]?\\d{4}(?!\\d)");

  private static final Pattern RESIDENT_NUMBER =
      Pattern.compile(
          "(?<!\\d)\\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\\d|3[01])\\s*-?\\s*[1-8]\\d{6}(?!\\d)");

  private PersonalInfo() {}

  /** 휴대폰 번호나 주민등록번호처럼 보이는 글이 있으면 true. */
  public static boolean contains(String text) {
    return MOBILE.matcher(text).find() || RESIDENT_NUMBER.matcher(text).find();
  }
}
