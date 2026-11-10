package kr.mujuthaek.api.common.dto.response;

import java.util.List;
import java.util.function.Function;
import kr.mujuthaek.api.common.pagination.CursorCodec;
import kr.mujuthaek.api.common.pagination.CursorKey;

/** 커서 방식 목록 응답. 조회는 size + 1개를 가져와서 다음 페이지가 있는지 판단해요. */
public record CursorPageResponse<T>(List<T> items, String nextCursor, boolean hasNext) {

  public static <R, T> CursorPageResponse<T> from(
      List<R> rows, int size, Function<R, T> mapper, Function<R, CursorKey> keyOf) {
    boolean hasNext = rows.size() > size;
    List<R> page = hasNext ? rows.subList(0, size) : rows;
    String next = hasNext ? CursorCodec.encode(keyOf.apply(page.get(page.size() - 1))) : null;
    return new CursorPageResponse<>(page.stream().map(mapper).toList(), next, hasNext);
  }
}
