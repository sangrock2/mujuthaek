package kr.mujuthaek.api.chat.service;

import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.chat.domain.ChatRoom;

/** 채팅방 찾기. 공고 모듈에 물어요 ({@link NoticeChatRooms}). 테스트는 가짜로 바꿔 끼워요. */
public interface ChatRooms {

  /** 공개된 공고의 채팅방. 다른 공고에 합쳐진 공고면 남은 공고의 방. 숨김·공개 전·없는 공고면 빈 값. */
  Optional<ChatRoom> find(UUID noticeId);
}
