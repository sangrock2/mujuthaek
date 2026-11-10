package kr.mujuthaek.api.notification.service.internal;

import java.util.UUID;

/**
 * 알림 받을 회원 한 명. 알림함에는 늘 남고, 푸시·이메일은 아래 값에 따라 보내요 (notification.requested의 recipients[] 한 칸).
 *
 * @param email 이메일로 보낼 주소. 이메일을 켰고 이 종류를 켰고 인증된 주소일 때만, 아니면 null
 * @param pushEnabled 이 종류 알림을 켰나 (종류별 켬·끔). 켰고 구독 기기가 있으면 웹 푸시로 보내요
 */
public record Recipient(UUID userId, String email, boolean quietEnabled, boolean pushEnabled) {

  /** 푸시를 받는 회원 (이메일 없음) */
  public static Recipient push(UUID userId, boolean quietEnabled) {
    return new Recipient(userId, null, quietEnabled, true);
  }

  @Override
  public String toString() {
    return "Recipient[userId="
        + userId
        + ", quietEnabled="
        + quietEnabled
        + ", pushEnabled="
        + pushEnabled
        + "]";
  }
}
