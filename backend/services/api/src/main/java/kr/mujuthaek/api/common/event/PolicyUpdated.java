package kr.mujuthaek.api.common.event;

import java.util.List;
import java.util.UUID;

/**
 * 공개된 창업지원 사업·사업공간 모집의 새 수집 버전에서 사용자가 볼 내용이 바뀜. 바뀐 값 자체는 싣지 않으니
 * NoticeQueryService.findPolicySummary로 조회하세요. notification이 받아 관심 정책으로 둔 회원에게 정정 알림을 보내요. 같은 버전을
 * 검수자가 승인해 바꾼 것은 보내지 않아요.
 *
 * <p>changedFields는 바뀐 부분의 이름이에요 (이 순서로): basic(제목) · region(지원 지역) · schedule(신청 기간·상시 여부) ·
 * conditions(판정 틀의 자격·우대 조건) · application(원문 주소·문의처·접수 방법). 판정 틀의 메모(notes)·기준일만 바뀐 것은 넣지 않아요 (다시
 * 추출할 때마다 정정 알림이 가지 않게).
 *
 * @param policyId 정책 ID (rawPolicyId)
 * @param field STARTUP_SUPPORT · SPACE_RECRUITMENT
 * @param version 반영한 수집 버전 (policy_judgments.raw_version). 정정 알림 중복 방지 열쇠에 써요
 * @param reprocess 과거 자료 재처리 중 바뀐 것이면 true (사용자 알림을 보내지 않아요)
 */
public record PolicyUpdated(
    UUID policyId, String field, int version, List<String> changedFields, boolean reprocess) {}
