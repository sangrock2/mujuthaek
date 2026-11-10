package kr.mujuthaek.api.notice.dto.response;

/**
 * 관리자 사이드바·개요의 혜택 검수 숫자.
 *
 * @param benefitPending 혜택 검수 대기 건수
 */
public record AdminBenefitReviewCountsResponse(int benefitPending) {}
