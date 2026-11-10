package kr.mujuthaek.api.notification.dto.response;

import java.time.Instant;
import java.util.UUID;

/**
 * 알림함 한 줄.
 *
 * @param type NEW_NOTICE · NEW_SUPPORT · DEADLINE_D3 · DEADLINE_D1 · CORRECTED · FOLLOW_UP ·
 *     REPORT_ANSWERED
 * @param target 가리킨 대상. 일반 제보 답변처럼 대상이 없으면 null
 * @param linkPath 누르면 갈 PWA 화면 (/notices/{id} …, 일반 제보 답변은 /me?tab=reports)
 * @param readAt 읽은 시각. 안 읽었으면 null
 */
public record NotificationItemResponse(
    UUID id,
    String type,
    Target target,
    String title,
    String body,
    String linkPath,
    Instant createdAt,
    Instant readAt) {

  /**
   * @param type NOTICE · BENEFIT · STARTUP_SUPPORT · SPACE_RECRUITMENT
   */
  public record Target(String type, UUID id) {}
}
