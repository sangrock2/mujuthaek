package kr.mujuthaek.api.notice.dto.response;

/**
 * 승인·반려 결과.
 *
 * @param reviewStatus APPROVED · REJECTED
 * @param eventId 검수 결정에 따라 발행할 이벤트 ID. 발행하지 않는 결정은 null.
 */
public record AdminReviewDecisionResponse(String id, String reviewStatus, String eventId) {}
