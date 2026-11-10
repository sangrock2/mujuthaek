package kr.mujuthaek.api.user.service;

/**
 * 알림 요청을 만들 때 쓰는 회원 설정 (UserNotificationQueryService.preferences).
 *
 * @param quietEnabled 22:00~08:00 알림을 08:00에
 */
public record NotificationPreference(
    boolean newNotice,
    boolean newSupport,
    boolean deadline,
    boolean correction,
    boolean followUp,
    boolean quietEnabled) {

  /** 줄이 없는 회원 */
  public static final NotificationPreference DEFAULT =
      new NotificationPreference(true, true, true, true, true, false);

  /** 이 종류(notification.requested type)를 푸시·이메일로 받나. 모르는 종류면 false */
  public boolean enabled(String type) {
    return switch (type) {
      case "NEW_NOTICE" -> newNotice;
      case "NEW_SUPPORT" -> newSupport;
      case "DEADLINE_D3", "DEADLINE_D1" -> deadline;
      case "CORRECTED" -> correction;
      case "FOLLOW_UP" -> followUp;
      case "REPORT_ANSWERED" -> true; // 본인이 보낸 제보의 답장이라 끄는 설정이 없어요 (조용한 시간은 따라요)
      default -> false;
    };
  }
}
