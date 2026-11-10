package kr.mujuthaek.api.notice.dto.response;

import java.time.OffsetDateTime;
import java.util.List;

/**
 * 관리자 검수 대기열 한 페이지: 공고·혜택 검수를 들어온 시각 순(오래된 것부터)으로 섞어요. 다음 페이지는 nextCursor로 받아요.
 *
 * @param total 이 조건(사유)의 대기 건수. 첫 페이지(cursor 없이)에서만 정확해요 — 다 받은 쪽은 다음 페이지부터 다시 세지 않아요
 * @param nextCursor 다음 페이지를 받을 값 (더 없으면 null)
 */
public record AdminReviewQueueResponse(int total, List<Item> items, String nextCursor) {

  /**
   * 대기 한 건.
   *
   * @param kind NOTICE 공고 검수(GET /api/admin/reviews/{id}) · BENEFIT 혜택 검수(GET
   *     /api/admin/benefit-reviews/{id})
   * @param id 검수 ID (상세·승인·반려에 써요)
   * @param reason MUST 공개 전 꼭 볼 것(혜택은 정책 제보로 다시 연 건) · CHECK 확인 필요 · FORMAT 원본 자료 문제(공고만)
   * @param title 제목
   * @param sourceCode 수집 출처 코드 (예: lh_myhome · youth)
   * @param rawVersion 원문 버전
   * @param queuedAt 검수 대기에 들어온 시각
   */
  public record Item(
      String kind,
      String id,
      String reason,
      String title,
      String sourceCode,
      Integer rawVersion,
      OffsetDateTime queuedAt) {}
}
