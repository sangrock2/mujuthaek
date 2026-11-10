package kr.mujuthaek.api.chat.event;

import java.util.UUID;
import kr.mujuthaek.api.chat.domain.ChatRoom;
import kr.mujuthaek.api.chat.service.ChatRooms;
import kr.mujuthaek.api.chat.service.ChatSseHub;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * 커밋된 채팅 변경만 방의 SSE 연결로 보내요. 이벤트의 공고 ID는 방 ID로 바꿔 보내요: 합치기 전에 쓴 메시지는 합쳐진 공고 ID에 남아 있어, 그 메시지의
 * 삭제·좋아요·가림·복원을 메시지의 공고 ID로 보내면 남은 방을 보는 사람에게 가지 않았어요(2026-11-10 재검토). 방을 못 찾으면(숨김 등) 받은 ID 그대로.
 */
@Component
class ChatEventRelay {

  private static final Logger log = LoggerFactory.getLogger(ChatEventRelay.class);

  private final ChatSseHub hub;
  private final ChatRooms rooms;

  ChatEventRelay(ChatSseHub hub, ChatRooms rooms) {
    this.hub = hub;
    this.rooms = rooms;
  }

  @TransactionalEventListener
  void on(ChatEvent event) {
    hub.broadcast(
        new ChatEvent(roomOf(event.noticeId()), event.name(), event.messageId(), event.data()));
  }

  private UUID roomOf(UUID noticeId) {
    try {
      return rooms.find(noticeId).map(ChatRoom::noticeId).orElse(noticeId);
    } catch (RuntimeException e) { // 방 찾기 실패로 커밋된 변경의 알림까지 막지 않아요
      log.warn("채팅 이벤트의 방을 찾지 못해 받은 공고 ID로 보냅니다: {}", e.toString());
      return noticeId;
    }
  }
}
