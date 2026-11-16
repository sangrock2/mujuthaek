package kr.mujuthaek.api.chat.event;

import kr.mujuthaek.api.chat.service.ChatService;
import kr.mujuthaek.api.common.event.UserNicknameReplaced;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * 실명일 수 있는 닉네임을 별칭으로 바꾸면 그 회원이 쓴 지난 채팅 글의 작성자 이름도 바꿔요(2026-11-16 보안 감사 L-8). 닉네임을 바꾸는 로그인 트랜잭션과
 * 같이(커밋 직전) 바꿔서, 실패하면 둘 다 되돌려져요.
 */
@Component
class ChatNicknameListener {

  private final ChatService chats;

  ChatNicknameListener(ChatService chats) {
    this.chats = chats;
  }

  @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT, fallbackExecution = true)
  void on(UserNicknameReplaced event) {
    chats.renameAuthor(event.userId(), event.nickname());
  }
}
