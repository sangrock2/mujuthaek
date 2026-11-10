package kr.mujuthaek.api.notification.event;

import java.util.Map;
import kr.mujuthaek.api.common.event.UserWithdrawn;
import kr.mujuthaek.api.common.messaging.Outbox;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * 회원 탈퇴(UserWithdrawn)를 알림 서버에 user.withdrawn으로 알려요 (contracts/schemas/notification-events.draft.md
 * 4장). 알림 서버는 그 회원의 발송 기록(안 보낸 줄 포함)을 지워요. 회원 삭제와 같은 트랜잭션(BEFORE_COMMIT)에서 아웃박스에 적어서, 삭제가 되돌려지면 알림도
 * 나가지 않고 삭제가 커밋되면 알림 서버가 꺼져 있어도 나중에 꼭 받아요. 회원 ID만 보내요.
 */
@Component
class UserWithdrawnExporter {

  private static final Logger log = LoggerFactory.getLogger(UserWithdrawnExporter.class);

  static final String EVENT_TYPE = "user.withdrawn";

  private final Outbox outbox;

  UserWithdrawnExporter(Outbox outbox) {
    this.outbox = outbox;
  }

  @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
  void on(UserWithdrawn event) {
    outbox.add(EVENT_TYPE, 1, Map.of("userId", event.userId()));
    log.info("탈퇴를 알림 서버에 알릴 이벤트를 아웃박스에 적음: userId={}", event.userId());
  }
}
