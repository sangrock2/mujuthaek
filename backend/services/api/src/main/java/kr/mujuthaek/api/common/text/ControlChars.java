package kr.mujuthaek.api.common.text;

/**
 * 사람이 쓴 글에 들어 있으면 안 되는 제어 문자 검사. 줄바꿈(\n, \r)과 탭은 괜찮아요.
 *
 * <p>NUL(U+0000)은 PostgreSQL이 글자로 받지 않아서, 채팅·신고·제보에 넣으면 400이 아니라 DB 오류로 500과 운영 경보가 났어요(2026-11-16
 * 보안 감사 L-12). 다른 제어 문자도 화면에서 쓸 일이 없어 같이 막아요.
 */
public final class ControlChars {

  private ControlChars() {}

  /** 줄바꿈·탭이 아닌 제어 문자가 있으면 true. null은 false */
  public static boolean present(String text) {
    if (text == null) {
      return false;
    }
    for (int i = 0; i < text.length(); i++) {
      char c = text.charAt(i);
      if (Character.isISOControl(c) && c != '\n' && c != '\r' && c != '\t') {
        return true;
      }
    }
    return false;
  }

  /** 하나라도 있으면 true */
  public static boolean anyPresent(String... texts) {
    for (String text : texts) {
      if (present(text)) {
        return true;
      }
    }
    return false;
  }
}
