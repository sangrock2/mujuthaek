package kr.mujuthaek.api.common.pagination;

import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.Objects;
import java.util.UUID;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;

/**
 * 커서 = 마지막 항목의 (정렬 이름, 정렬 값, ID). 같은 정렬 값이어도 ID로 순서가 정해져요.
 *
 * @param sort 이 커서를 만든 정렬 (예: DEADLINE, LATEST). 다른 정렬의 커서는 받지 않아요
 * @param value 정렬 값을 글자로 (마감일 2026-10-31, 시각 2026-10-22T03:00:00Z …). 값이 없는 항목은 빈 글자
 */
public record CursorKey(String sort, String value, UUID id) {

  public CursorKey {
    Objects.requireNonNull(sort, "sort");
    Objects.requireNonNull(id, "id");
    value = value == null ? "" : value;
  }

  public static CursorKey of(String sort, Object value, UUID id) {
    return new CursorKey(sort, value == null ? null : value.toString(), id);
  }

  /**
   * 정렬 값이 목록 안 위치(0부터)인 커서의 위치. 서버가 계산해서 DB 정렬을 쓸 수 없는 목록(주택목록, 판정 결과 순서)에서 써요. 숫자가 아니거나 음수·너무 큰
   * 값(조작한 커서)이면 400 INVALID_CURSOR예요 — 그대로 쓰면 목록 범위를 벗어나 500이 나요.
   */
  public int position() {
    try {
      int position = Integer.parseInt(value);
      if (position < 0 || position == Integer.MAX_VALUE) {
        throw invalid();
      }
      return position;
    } catch (NumberFormatException e) {
      throw invalid();
    }
  }

  /**
   * 정렬 값이 날짜(2026-10-31)인 커서의 날짜. 날짜가 아니거나 1~9999년을 벗어나면(조작한 커서) 400 INVALID_CURSOR예요 — 그대로 SQL의
   * {@code cast(… as date)}에 넣으면 DB 오류로 500과 운영 경보가 났어요(2026-11-16 보안 감사 L-12).
   */
  public LocalDate date() {
    try {
      LocalDate date = LocalDate.parse(value);
      if (date.getYear() < 1 || date.getYear() > 9999) {
        throw invalid();
      }
      return date;
    } catch (DateTimeParseException e) {
      throw invalid();
    }
  }

  private static CustomException invalid() {
    return new CustomException(ErrorCode.INVALID_CURSOR, ErrorCode.INVALID_CURSOR.message());
  }
}
