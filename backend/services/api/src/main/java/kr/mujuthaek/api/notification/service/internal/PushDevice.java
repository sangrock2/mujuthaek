package kr.mujuthaek.api.notification.service.internal;

/**
 * 알림 요청에 실어 보낼 구독 기기 한 대 (notification.requested의 recipients[].push 한 칸). 알면 그 기기에 알림을 보낼 수 있는 값이라
 * toString을 가려요.
 */
public record PushDevice(String endpoint, String p256dh, String auth) {

  @Override
  public String toString() {
    return "PushDevice[***]";
  }
}
