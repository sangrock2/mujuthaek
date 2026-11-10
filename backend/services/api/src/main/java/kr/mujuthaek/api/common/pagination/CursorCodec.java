package kr.mujuthaek.api.common.pagination;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.UUID;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;

/** 커서를 URL에 넣기 좋은 문자열(Base64URL)로 바꾸고 되돌려요. */
public final class CursorCodec {

  private static final String SEPARATOR = "|";

  private CursorCodec() {}

  public static String encode(CursorKey key) {
    String raw = key.sort() + SEPARATOR + key.value() + SEPARATOR + key.id();
    return Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(raw.getBytes(StandardCharsets.UTF_8));
  }

  /** 커서가 없으면 null (첫 페이지). 읽을 수 없거나 다른 정렬로 만든 커서면 400 INVALID_CURSOR — 정렬·필터를 바꾸면 처음부터 다시 받아요. */
  public static CursorKey decode(String cursor, String expectedSort) {
    if (cursor == null || cursor.isBlank()) {
      return null;
    }
    CursorKey key;
    try {
      String raw = new String(Base64.getUrlDecoder().decode(cursor), StandardCharsets.UTF_8);
      int first = raw.indexOf(SEPARATOR);
      int last = raw.lastIndexOf(SEPARATOR);
      if (first < 0 || first == last) {
        throw new IllegalArgumentException("칸이 모자라요");
      }
      key =
          new CursorKey(
              raw.substring(0, first),
              raw.substring(first + 1, last),
              UUID.fromString(raw.substring(last + 1)));
    } catch (RuntimeException e) {
      throw invalid();
    }
    if (!key.sort().equals(expectedSort)) {
      throw invalid();
    }
    return key;
  }

  private static CustomException invalid() {
    return new CustomException(ErrorCode.INVALID_CURSOR, ErrorCode.INVALID_CURSOR.message());
  }
}
