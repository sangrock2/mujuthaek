package kr.mujuthaek.notification.notification;

/**
 * 알림 종류 (notifications.type). api가 notification.requested의 payload.type으로 정해 보내요.
 *
 * <p>{@code digest}는 "채널이 모아서 보내는 종류"예요. 이메일은 하루 두 번(08:00·18:00), 웹 푸시는 30분마다 묶어요 (DigestCadence).
 */
public enum NotificationType {
  NEW_NOTICE(true),
  NEW_SUPPORT(true),
  DEADLINE_D3(false),
  DEADLINE_D1(false),
  CORRECTED(false),
  FOLLOW_UP(false),
  REPORT_ANSWERED(false); // 회원이 보낸 제보에 관리자가 답함 (제보한 회원 한 명)

  private final boolean digest;

  NotificationType(boolean digest) {
    this.digest = digest;
  }

  public boolean digest() {
    return digest;
  }
}
