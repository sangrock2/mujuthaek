package kr.mujuthaek.api.notice.dto.response;

/**
 * 관리자 개요의 검수 품질·오늘 처리.
 *
 * @param days 최근 며칠 기준인지
 * @param recent 최근 days일
 * @param today 오늘(한국 시간)
 */
public record AdminReviewStatsResponse(int days, Window recent, Window today) {

  /**
   * 한 기간의 처리 수.
   *
   * @param approved 그대로 승인
   * @param editedApproved 고쳐서 승인
   * @param rejected 반려
   * @param asIsRate 그대로 승인 비율(%), 처리한 건이 없으면 null. 고쳐서 승인·반려 비율도 같은 방식
   * @param medianMinutes 들어와서 처리되기까지 걸린 시간의 중앙값(분), 처리한 건이 없으면 null
   */
  public record Window(
      int approved,
      int editedApproved,
      int rejected,
      Integer asIsRate,
      Integer editedRate,
      Integer rejectedRate,
      Integer medianMinutes) {}
}
