package kr.mujuthaek.api.notice.service.internal;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import kr.mujuthaek.api.common.event.AreaScoresCalculated.Score;
import org.junit.jupiter.api.Test;

class NoticeAreaScoreServiceTest {

  private static final Instant AT = Instant.parse("2026-10-19T01:00:00Z");

  @Test
  void 위치_종류_범위_계산정보가_모두_있어야_저장한다() {
    assertThat(NoticeAreaScoreService.valid(new Score("loc", "LIVING", 0, AT, "v1"))).isTrue();
    assertThat(NoticeAreaScoreService.valid(new Score("loc", "COMMERCIAL", 100, AT, "v1")))
        .isTrue();

    assertThat(NoticeAreaScoreService.valid(new Score(null, "LIVING", 50, AT, "v1"))).isFalse();
    assertThat(NoticeAreaScoreService.valid(new Score(" ", "LIVING", 50, AT, "v1"))).isFalse();
    assertThat(NoticeAreaScoreService.valid(new Score("loc", "COMMUTE", 50, AT, "v1"))).isFalse();
    assertThat(NoticeAreaScoreService.valid(new Score("loc", "LIVING", -1, AT, "v1"))).isFalse();
    assertThat(NoticeAreaScoreService.valid(new Score("loc", "LIVING", 100.5, AT, "v1"))).isFalse();
    assertThat(NoticeAreaScoreService.valid(new Score("loc", "LIVING", 50, null, "v1"))).isFalse();
    assertThat(NoticeAreaScoreService.valid(new Score("loc", "LIVING", 50, AT, null))).isFalse();
    assertThat(NoticeAreaScoreService.valid(new Score("loc", "LIVING", 50, AT, " "))).isFalse();
  }
}
