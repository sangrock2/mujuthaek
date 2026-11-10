package kr.mujuthaek.api.chat.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.time.LocalDate;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.chat.domain.ChatRoom;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import kr.mujuthaek.api.notice.service.NoticeSummary;
import org.junit.jupiter.api.Test;

/** 공고 요약으로 방을 만들어요: 합쳐진 공고는 남은 공고의 방, 없는 공고는 빈 값. */
class NoticeChatRoomsTest {

  private final NoticeQueryService notices = mock(NoticeQueryService.class);
  private final NoticeChatRooms rooms = new NoticeChatRooms(notices);

  @Test
  void mergedNoticeOpensTheSurvivingRoomWithItsDeadline() {
    UUID merged = UUID.randomUUID();
    UUID kept = UUID.randomUUID();
    when(notices.findSummary(merged))
        .thenReturn(
            Optional.of(
                new NoticeSummary(
                    kept,
                    2,
                    "HOUSING",
                    "행복주택 입주자 모집",
                    "LH",
                    "HAPPY_HOUSING",
                    "APPLYING",
                    LocalDate.of(2026, 10, 20),
                    LocalDate.of(2026, 10, 31),
                    List.of(),
                    true,
                    "/notices/" + kept,
                    null)));

    assertThat(rooms.find(merged)).contains(new ChatRoom(kept, LocalDate.of(2026, 10, 31)));
    assertThat(rooms.find(UUID.randomUUID())).isEmpty();

    // 2026-11-10 코드 검토: 합치기 전 메시지는 합쳐진 공고 ID에 남아 있어 방이 그 ID도 함께 읽어요(예전엔 기록이 사라짐)
    when(notices.mergedFrom(kept)).thenReturn(List.of(merged));
    assertThat(rooms.find(merged).orElseThrow().noticeIds()).containsExactly(kept, merged);
  }

  @Test
  void readOnlyStartsThirtyOneDaysAfterTheDeadline() {
    ChatRoom room = new ChatRoom(UUID.randomUUID(), LocalDate.of(2026, 10, 1));

    assertThat(room.readOnlyFrom()).isEqualTo(LocalDate.of(2026, 11, 1));
    assertThat(room.readOnly(LocalDate.of(2026, 10, 31))).isFalse();
    assertThat(room.readOnly(LocalDate.of(2026, 11, 1))).isTrue();
    // 상시 공고는 읽기 전용이 되지 않아요
    assertThat(new ChatRoom(UUID.randomUUID(), null).readOnly(LocalDate.of(2099, 1, 1))).isFalse();
  }
}
