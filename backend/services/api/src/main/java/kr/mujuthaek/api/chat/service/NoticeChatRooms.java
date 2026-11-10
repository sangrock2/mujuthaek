package kr.mujuthaek.api.chat.service;

import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.chat.domain.ChatRoom;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import org.springframework.stereotype.Component;

/** 공고 요약({@link NoticeQueryService#findSummary})으로 방 ID(합쳐졌으면 남은 공고 ID)와 접수 마감일을 받아요. */
@Component
class NoticeChatRooms implements ChatRooms {

  private final NoticeQueryService notices;

  NoticeChatRooms(NoticeQueryService notices) {
    this.notices = notices;
  }

  /** 합쳐진 공고 ID도 함께 넣어요: 합치기 전 메시지는 그 ID에 남아 있어, 남은 공고 ID로만 읽으면 채팅 기록이 사라졌어요(2026-11-10 코드 검토). */
  @Override
  public Optional<ChatRoom> find(UUID noticeId) {
    return notices
        .findSummary(noticeId)
        .map(n -> new ChatRoom(n.noticeId(), n.applyEnd(), notices.mergedFrom(n.noticeId())));
  }
}
