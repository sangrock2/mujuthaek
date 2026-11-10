package kr.mujuthaek.api.common.event;

import java.util.List;
import java.util.UUID;

/**
 * 새 창업지원 사업·사업공간 모집이 공개됨 (notice.policy_judgments에 처음 저장한 때 한 번). 검수 대기(IN_REVIEW)라 저장하지 않던 정책은
 * 승인되어 처음 저장될 때 보내요. notification(사용자 알림)이 받아 관심 조건이 맞는 회원에게 알려요. 과거 자료 재처리(reprocess)는 알리지 않아요.
 * 마감일 등 알림에 쓸 다른 값은 NoticeQueryService.findPolicySummary로 조회하세요.
 *
 * @param policyId 정책 ID (수집 DB 정책 ID, rawPolicyId)
 * @param field STARTUP_SUPPORT · SPACE_RECRUITMENT
 * @param regionCodes 지원 지역 5자리 (시도 전체는 xx000). 전국이면 빈 목록
 */
public record PolicyPublished(
    UUID policyId, String field, List<String> regionCodes, String title, boolean reprocess) {}
