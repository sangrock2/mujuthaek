package kr.mujuthaek.api.notice.event;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import kr.mujuthaek.api.notice.service.internal.NoticeBackfillService.Kind;
import org.junit.jupiter.api.Test;

class NoticeBackfillCommandTest {

  @Test
  void 보낼_이벤트_종류를_읽는다() {
    assertThat(NoticeBackfillCommand.kinds("published, LOCATIONS"))
        .containsExactlyInAnyOrder(Kind.PUBLISHED, Kind.LOCATIONS);
    assertThat(NoticeBackfillCommand.kinds("locations,")).containsExactly(Kind.LOCATIONS);
  }

  @Test
  void 모르는_종류나_빈_값은_거절한다() {
    assertThatThrownBy(() -> NoticeBackfillCommand.kinds("closed"))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> NoticeBackfillCommand.kinds(" , "))
        .isInstanceOf(IllegalArgumentException.class);
  }
}
