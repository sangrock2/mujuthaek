package kr.mujuthaek.api.common.event;

import java.util.UUID;

/**
 * 관리자가 생활권 제보를 처리하고 답을 남김. 답장을 보내는 쪽(notification)이 받아 제보한 회원에게 알려요.
 *
 * @param field 제보한 항목 이름 (역까지 거리 등)
 * @param result FIXED 고침 · KEPT 그대로 둠
 * @param targetTitle 항상 null. area는 공고 제목을 모르고 notice를 부를 수 없어요. 제목이 필요하면 받는 쪽이 noticeId로
 *     NoticeQueryService.findSummaries에서 찾아요
 */
public record AreaReportAnswered(
    UUID reportId,
    UUID noticeId,
    UUID reporterId,
    String field,
    String result,
    String reply,
    String targetTitle)
    implements ReportAnswered {}
