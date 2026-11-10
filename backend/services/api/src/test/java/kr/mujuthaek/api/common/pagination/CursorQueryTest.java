package kr.mujuthaek.api.common.pagination;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.common.dto.response.CursorPageResponse;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import org.junit.jupiter.api.Test;

class CursorQueryTest {

  @Test
  void firstPageUsesDefaultSize() {
    CursorQuery q = CursorQuery.of(null, null, "DEADLINE");
    assertThat(q.after()).isNull();
    assertThat(q.size()).isEqualTo(20);
    assertThat(q.fetchSize()).isEqualTo(21);
  }

  @Test
  void sizeMustBeBetween1And100() {
    assertThat(CursorQuery.of(null, 100, "LATEST").size()).isEqualTo(100);
    for (int bad : new int[] {0, 101, -1}) {
      assertThatThrownBy(() -> CursorQuery.of(null, bad, "LATEST"))
          .isInstanceOfSatisfying(
              CustomException.class,
              e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.VALIDATION_FAILED));
    }
  }

  @Test
  void cursorRoundTripsWithItsSort() {
    UUID id = UUID.randomUUID();
    String cursor = CursorCodec.encode(CursorKey.of("DEADLINE", LocalDate.of(2026, 10, 31), id));

    assertThat(CursorQuery.of(cursor, 10, "DEADLINE").after())
        .isEqualTo(new CursorKey("DEADLINE", "2026-10-31", id));
  }

  @Test
  void cursorFromAnotherSortOrGarbageIsInvalid() {
    String latest = CursorCodec.encode(CursorKey.of("LATEST", "2026-10-22", UUID.randomUUID()));
    for (String cursor : List.of(latest, "not-a-cursor", "fHw")) {
      assertThatThrownBy(() -> CursorQuery.of(cursor, 10, "DEADLINE"))
          .isInstanceOfSatisfying(
              CustomException.class,
              e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.INVALID_CURSOR));
    }
  }

  @Test
  void itemsWithoutASortValueStillGetACursor() {
    UUID id = UUID.randomUUID();
    String cursor = CursorCodec.encode(CursorKey.of("DEADLINE", null, id));
    assertThat(CursorCodec.decode(cursor, "DEADLINE")).isEqualTo(new CursorKey("DEADLINE", "", id));
  }

  @Test
  void pageResponseUsesTheExtraRowToKnowIfThereIsMore() {
    List<Integer> rows = List.of(1, 2, 3);
    var page =
        CursorPageResponse.from(
            rows, 2, n -> "#" + n, n -> CursorKey.of("LATEST", n, new UUID(0, n)));

    assertThat(page.items()).containsExactly("#1", "#2");
    assertThat(page.hasNext()).isTrue();
    assertThat(CursorCodec.decode(page.nextCursor(), "LATEST").value()).isEqualTo("2");
    assertThat(
            CursorPageResponse.from(rows, 3, n -> n, n -> CursorKey.of("LATEST", n, new UUID(0, n)))
                .nextCursor())
        .isNull();
  }
}
