package kr.mujuthaek.api.notice.dto.response;

import java.time.OffsetDateTime;

/**
 * 관리자 사이드바·개요의 검수 숫자.
 *
 * @param reviewPending 검수 대기 건수
 * @param oldestReceivedAt 가장 오래 기다린 건이 들어온 시각 (대기가 없으면 null)
 */
public record AdminReviewCountsResponse(int reviewPending, OffsetDateTime oldestReceivedAt) {}
