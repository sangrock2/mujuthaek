package kr.mujuthaek.api.common.event;

import java.util.UUID;

/**
 * 관리자가 주거·복지 정책(혜택) 제보를 처리하고 답을 남김. 답장을 보내는 쪽(notification)이 받아 제보한 회원에게 알려요.
 *
 * @param policyId 혜택 정책 원본 ID (policy.extracted의 rawPolicyId)
 * @param result FIXED 고침 · KEPT 그대로 둠
 * @param targetTitle 혜택 정책 제목 (제보 때 받아 둔 값)
 */
public record BenefitReportAnswered(
    UUID reportId,
    UUID policyId,
    UUID reporterId,
    String field,
    String result,
    String reply,
    String targetTitle)
    implements ReportAnswered {}
