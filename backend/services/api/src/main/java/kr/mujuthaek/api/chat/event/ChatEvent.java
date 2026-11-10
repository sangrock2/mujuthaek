package kr.mujuthaek.api.chat.event;

import java.util.UUID;
import kr.mujuthaek.api.chat.dto.response.ChatMessageResponse;

/**
 * 채팅방에 SSE로 보낼 일. 서비스가 트랜잭션 안에서 발행하고, 커밋된 뒤에만 {@link ChatEventRelay}가 방의 연결로 보내요 (롤백된 메시지가 화면에 나오지
 * 않게).
 *
 * @param noticeId 채팅방 (공고 ID)
 * @param name SSE event 이름
 * @param messageId SSE id. message.created만 넣어요 (재연결 때 Last-Event-ID로 놓친 메시지를 이어 받게)
 * @param data SSE data (JSON)
 */
public record ChatEvent(UUID noticeId, String name, UUID messageId, Object data) {

  /** 삭제·가림 이벤트의 data. */
  public record MessageRef(UUID id) {}

  /** 좋아요 수 이벤트의 data. */
  public record LikeCount(UUID id, int likeCount) {}

  public static ChatEvent created(ChatMessageResponse message) {
    return new ChatEvent(message.noticeId(), "message.created", message.id(), message);
  }

  public static ChatEvent deleted(UUID noticeId, UUID messageId) {
    return new ChatEvent(noticeId, "message.deleted", null, new MessageRef(messageId));
  }

  public static ChatEvent hidden(UUID noticeId, UUID messageId) {
    return new ChatEvent(noticeId, "message.hidden", null, new MessageRef(messageId));
  }

  public static ChatEvent restored(ChatMessageResponse message) {
    return new ChatEvent(message.noticeId(), "message.restored", null, message);
  }

  public static ChatEvent likeUpdated(UUID noticeId, UUID messageId, int likeCount) {
    return new ChatEvent(noticeId, "like.updated", null, new LikeCount(messageId, likeCount));
  }
}
