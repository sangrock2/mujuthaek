package kr.mujuthaek.api.common.pagination;

import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;

/**
 * 목록 요청의 cursor·size. size는 기본 20, 1~100이에요.
 *
 * <p>컨트롤러에서 {@code @RequestParam(required = false) String cursor, @RequestParam(required = false)
 * Integer size}로 받아 {@link #of}로 만들어요. 조회는 {@code size + 1}개를 가져와 {@code CursorPageResponse.from}에
 * 넘겨요.
 *
 * @param after 이 항목 다음부터 (첫 페이지면 null)
 */
public record CursorQuery(CursorKey after, int size) {

  public static final int DEFAULT_SIZE = 20;
  public static final int MAX_SIZE = 100;

  /**
   * @param sort 지금 요청의 정렬. 커서가 다른 정렬로 만든 것이면 400 INVALID_CURSOR
   */
  public static CursorQuery of(String cursor, Integer size, String sort) {
    int checked = size == null ? DEFAULT_SIZE : size;
    if (checked < 1 || checked > MAX_SIZE) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "size는 1~" + MAX_SIZE + " 사이여야 해요");
    }
    return new CursorQuery(CursorCodec.decode(cursor, sort), checked);
  }

  /** 다음 페이지가 있는지 알려고 하나 더 가져올 개수. */
  public int fetchSize() {
    return size + 1;
  }
}
