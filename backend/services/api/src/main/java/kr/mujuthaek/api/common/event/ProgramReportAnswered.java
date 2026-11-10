package kr.mujuthaek.api.common.event;

import java.util.UUID;

/**
 * 관리자가 창업지원 사업 제보를 처리하고 답을 남김. 답장을 보내는 쪽(notification)이 받아 제보한 회원에게 알려요.
 *
 * @param programId 창업지원 사업 ID (수집 DB 정책 ID, rawPolicyId)
 * @param result FIXED 고침 · KEPT 그대로 둠
 * @param targetTitle 창업지원 사업 제목
 */
public record ProgramReportAnswered(
    UUID reportId,
    UUID programId,
    UUID reporterId,
    String field,
    String result,
    String reply,
    String targetTitle)
    implements ReportAnswered {}
