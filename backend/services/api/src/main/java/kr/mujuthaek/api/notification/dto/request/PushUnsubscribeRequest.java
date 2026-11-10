package kr.mujuthaek.api.notification.dto.request;

/**
 * DELETE /api/users/me/push-subscriptions 본문. {@code subscription.toJSON()}을 그대로 보내도 돼요 (keys는 읽지
 * 않아요).
 *
 * @param endpoint 해제할 이 기기 주소
 */
public record PushUnsubscribeRequest(String endpoint) {

  @Override
  public String toString() {
    return "PushUnsubscribeRequest[endpoint=***]";
  }
}
