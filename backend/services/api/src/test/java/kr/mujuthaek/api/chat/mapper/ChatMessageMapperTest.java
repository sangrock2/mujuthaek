package kr.mujuthaek.api.chat.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.OffsetDateTime;
import java.util.UUID;
import kr.mujuthaek.api.chat.domain.MessageStatus;
import kr.mujuthaek.api.chat.repository.ChatMessageRepository.MessageRow;
import org.junit.jupiter.api.Test;

/** 지운 글·가린 글은 본문도 쓴 사람 이름도 내보내지 않아요 (2026-11-16 보안 감사 L-8). */
class ChatMessageMapperTest {

  private static MessageRow row(MessageStatus status, UUID parent, MessageStatus parentStatus) {
    return new MessageRow(
        UUID.randomUUID(),
        UUID.randomUUID(),
        UUID.randomUUID(),
        "홍길동",
        parent,
        "본문",
        0,
        0,
        status,
        OffsetDateTime.parse("2026-11-16T10:00:00+09:00"),
        parent == null ? null : "원글쓴이",
        parent == null ? null : "원글 본문",
        parentStatus,
        false);
  }

  @Test
  void visibleMessagesShowTheAuthor() {
    var response = ChatMessageMapper.toResponse(row(MessageStatus.VISIBLE, null, null), null);
    assertThat(response.authorNickname()).isEqualTo("홍길동");
    assertThat(response.content()).isEqualTo("본문");
  }

  @Test
  void deletedOrHiddenMessagesHideTheAuthor() {
    for (MessageStatus status : MessageStatus.values()) {
      if (status == MessageStatus.VISIBLE) continue;
      var response = ChatMessageMapper.toResponse(row(status, null, null), null);
      assertThat(response.authorNickname()).as(status.name()).isNull();
      assertThat(response.content()).as(status.name()).isNull();
    }
  }

  @Test
  void hiddenParentPreviewHidesItsAuthorToo() {
    for (MessageStatus status : MessageStatus.values()) {
      var response =
          ChatMessageMapper.toResponse(row(MessageStatus.VISIBLE, UUID.randomUUID(), status), null);
      boolean visible = status == MessageStatus.VISIBLE;
      assertThat(response.parent().authorNickname() != null).as(status.name()).isEqualTo(visible);
    }
  }
}
