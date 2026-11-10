package kr.mujuthaek.notification.delivery.push;

import java.time.Duration;
import kr.mujuthaek.notification.notification.NotificationRequest.PushDevice;

/**
 * 기기 한 대에 보낼 푸시 1건. 기기 주소·키가 들어 있어서 toString을 가려요.
 *
 * @param payload 서비스 워커가 받을 JSON (암호화 전)
 * @param ttl 기기가 꺼져 있을 때 푸시 서비스가 들고 있을 시간
 * @param urgency {@code high} 또는 {@code normal}
 */
public record PushMessage(PushDevice device, byte[] payload, Duration ttl, String urgency) {

  @Override
  public String toString() {
    return "PushMessage[device=***, bytes=" + payload.length + ", ttl=" + ttl + "]";
  }
}
