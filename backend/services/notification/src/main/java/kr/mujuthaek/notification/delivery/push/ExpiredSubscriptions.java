package kr.mujuthaek.notification.delivery.push;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.notification.outbox.Outbox;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * 죽은 구독(404·410)을 api에 알려요: push.subscription.expired (contracts/schemas/web-push.draft.md 5장).
 * api가 그 회원의 그 기기를 지워서, 다음 알림 요청부터 그 기기가 빠져요. 발송 결과를 남기는 트랜잭션 안에서 아웃박스에 적어요.
 */
@Component
class ExpiredSubscriptions {

  static final String EVENT_TYPE = "push.subscription.expired";

  private final Outbox outbox;

  ExpiredSubscriptions(Outbox outbox) {
    this.outbox = outbox;
  }

  @Transactional
  public void report(UUID userId, String endpoint, int status) {
    Map<String, Object> payload = new LinkedHashMap<>();
    payload.put("userId", userId);
    payload.put("endpoint", endpoint);
    payload.put("status", status);
    outbox.add(EVENT_TYPE, 1, payload);
  }
}
