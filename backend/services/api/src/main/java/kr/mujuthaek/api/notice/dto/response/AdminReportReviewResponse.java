package kr.mujuthaek.api.notice.dto.response;

import java.util.UUID;

/**
 * 제보로 다시 연 검수. 관리자는 reviewId로 검수 화면(GET /api/admin/reviews/{reviewId})에서 칸을 고쳐 승인한 뒤 제보를 끝내요.
 *
 * @param reopened false면 이미 대기 중이던 검수를 그대로 이은 것
 */
public record AdminReportReviewResponse(UUID reportId, UUID reviewId, boolean reopened) {}
