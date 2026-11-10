package kr.mujuthaek.api.chat.event;

import kr.mujuthaek.api.chat.service.ChatService;
import kr.mujuthaek.api.common.event.UserWithdrawn;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * 회원이 탈퇴하면 그 회원의 채팅 데이터를 지워요 (요구사항 3-16: 탈퇴 후 데이터 0건, notice·area 제보와 같은 방식). 탈퇴와 같은 트랜잭션(커밋 직전)에서
 * 지워, 실패하면 탈퇴도 되돌려져요(2026-11-10 코드 검토: 커밋 뒤 한 번만 돌아 실패하면 메시지가 남았음).
 */
@Component
class ChatWithdrawalListener {

  private final ChatService chats;

  ChatWithdrawalListener(ChatService chats) {
    this.chats = chats;
  }

  @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT, fallbackExecution = true)
  void on(UserWithdrawn event) {
    chats.forget(event.userId());
  }
}
