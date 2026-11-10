package kr.mujuthaek.api.notice.dto.response;

/**
 * 승인·반려 결과.
 *
 * @param reviewStatus APPROVED · REJECTED
 * @param pendingCount 처리 뒤 남은 대기 건수 (사이드바 숫자)
 */
public record AdminReviewDecisionResponse(String id, String reviewStatus, int pendingCount) {}
