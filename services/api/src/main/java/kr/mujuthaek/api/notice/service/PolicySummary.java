package kr.mujuthaek.api.notice.service;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

/**
 * 다른 모듈(알림·관심 정책)이 정책 ID로 조회하는 창업지원 사업·사업공간 모집 요약 (NoticeQueryService.findPolicySummary). 상세 API가
 * 없어서 화면은 판정 응답과 원문(detailUrl)으로 보여줘요.
 *
 * @param policyId 정책 ID (수집 DB 정책 ID, rawPolicyId)
 * @param version 수집 버전 (정정되면 올라가는 값)
 * @param field STARTUP_SUPPORT · SPACE_RECRUITMENT
 * @param organization 기관 이름 (출처 안내, 모르면 null)
 * @param status 신청 상태 UPCOMING · APPLYING · ALWAYS · CLOSED · UNKNOWN (마감된 정책도 줘요). UNKNOWN은 마감일을
 *     모르는데 상시도 아닌 정책으로 판정 목록에서 빠져요
 * @param applyEnd 신청 마감일 (상시거나 모르면 null)
 * @param regionCodes 지원 지역 5자리 (시도 전체는 xx000). 전국이면 빈 목록
 * @param detailUrl 수집한 정책 원문 주소 (모르면 null)
 * @param applyNote 마감일 대신 적힌 신청 기간 안내(「예산 소진 시까지」, 없으면 null). 알림 문구가 마감일이 없을 때 써요
 */
public record PolicySummary(
    UUID policyId,
    int version,
    String field,
    String title,
    String organization,
    String status,
    LocalDate applyStart,
    LocalDate applyEnd,
    List<String> regionCodes,
    String detailUrl,
    String applyNote) {}
