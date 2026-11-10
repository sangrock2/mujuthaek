package kr.mujuthaek.api.common.event;

import java.util.UUID;

/**
 * 관리자가 공고 제보를 처리하고 답을 남김. 답장을 보내는 쪽(notification)이 받아 제보한 회원에게 알려요. 제목 등은
 * NoticeQueryService.findSummaries로 조회하세요.
 *
 * @param reporterId 제보한 회원
 * @param field 제보한 칸 이름 (보증금 등)
 * @param result FIXED 고침 · KEPT 원문대로 그대로 둠
 * @param reply 회원에게 보낼 답
 * @param targetTitle 공고 제목
 */
public record NoticeReportAnswered(
    UUID reportId,
    UUID noticeId,
    UUID reporterId,
    String field,
    String result,
    String reply,
    String targetTitle)
    implements ReportAnswered {}
