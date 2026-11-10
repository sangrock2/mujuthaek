package kr.mujuthaek.api.notice.domain;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.notice.domain.BaseSource.Candidate;
import org.junit.jupiter.api.Test;

class BaseSourceTest {

  private static final UUID A = UUID.fromString("00000000-0000-7000-8000-00000000000a");
  private static final UUID B = UUID.fromString("00000000-0000-7000-8000-00000000000b");
  private static final Instant EARLY = Instant.parse("2026-10-01T00:00:00Z");
  private static final Instant LATE = Instant.parse("2026-10-02T00:00:00Z");

  private static UUID choose(Candidate... candidates) {
    return BaseSource.choose(List.of(candidates)).orElseThrow().root();
  }

  @Test
  void 공고문_PDF가_있는_출처가_먼저다() {
    assertThat(
            choose(
                new Candidate(A, false, LocalDate.of(2026, 10, 1), EARLY),
                new Candidate(B, true, LocalDate.of(2026, 10, 5), LATE)))
        .isEqualTo(B);
  }

  @Test
  void PDF가_같으면_먼저_게시된_출처_게시일을_모르면_뒤로() {
    assertThat(
            choose(
                new Candidate(A, true, LocalDate.of(2026, 10, 5), EARLY),
                new Candidate(B, true, LocalDate.of(2026, 10, 1), LATE)))
        .isEqualTo(B);
    assertThat(
            choose(
                new Candidate(A, true, null, EARLY),
                new Candidate(B, true, LocalDate.of(2026, 10, 9), LATE)))
        .isEqualTo(B);
  }

  @Test
  void 게시일도_같으면_먼저_들어온_출처_그다음_ID() {
    LocalDate day = LocalDate.of(2026, 10, 1);
    assertThat(choose(new Candidate(A, true, day, LATE), new Candidate(B, true, day, EARLY)))
        .isEqualTo(B);
    assertThat(choose(new Candidate(B, true, day, EARLY), new Candidate(A, true, day, EARLY)))
        .isEqualTo(A);
    // 모두 같으면 지금 기준을 유지
    assertThat(
            BaseSource.choose(
                    List.of(new Candidate(A, true, day, EARLY), new Candidate(B, true, day, EARLY)),
                    B)
                .orElseThrow()
                .root())
        .isEqualTo(B);
  }
}
