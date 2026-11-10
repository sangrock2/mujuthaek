package kr.mujuthaek.api.notification.dto.response;

import java.util.List;
import tools.jackson.databind.JsonNode;

/**
 * 관리자 「알림」 화면: 발송 결과와 봤는지·눌렀는지 (GET /api/admin/notifications/stats). 회원별 값은 없고 종류별 합계만 있어요.
 *
 * @param days 최근 며칠
 * @param delivery 알림 서버 발송 결과 {byType[{type, channel, sent, failed, pending}], failures[{channel,
 *     error, count}]}. 알림 서버에 닿지 못하면 null
 * @param engagement 알림함 지표 (종류별)
 */
public record AdminNotificationStatsResponse(
    int days, JsonNode delivery, List<Engagement> engagement) {

  /**
   * 알림 종류 하나의 지표.
   *
   * @param created 알림함에 남긴 수 (받는 회원 수)
   * @param shown 웹 푸시가 기기에 뜬 수
   * @param read 읽은 수 (알림 목록에서 읽거나 눌러 들어감)
   * @param clicked 푸시나 알림 목록에서 눌러 그 화면으로 간 수
   */
  public record Engagement(String type, long created, long shown, long read, long clicked) {}
}
