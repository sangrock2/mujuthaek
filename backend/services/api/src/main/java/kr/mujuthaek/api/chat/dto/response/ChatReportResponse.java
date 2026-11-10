package kr.mujuthaek.api.chat.dto.response;

import java.time.OffsetDateTime;
import java.util.UUID;
import kr.mujuthaek.api.chat.domain.MessageStatus;
import kr.mujuthaek.api.chat.domain.ReportReason;
import kr.mujuthaek.api.chat.domain.ReviewStatus;

/**
 * 관리자 신고 목록의 신고 하나. 신고한 회원은 보여주지 않아요.
 *
 * @param noticeId 메시지가 있는 채팅방 (공고 ID)
 * @param message 신고된 메시지. 가려지거나 작성자가 지운 메시지도 검토하려고 본문을 보여줘요
 * @param reviewedBy 처리한 관리자 회원 ID (검토 전이면 null)
 * @param reviewedAt 처리한 시각 (검토 전이면 null)
 */
public record ChatReportResponse(
    UUID reportId,
    UUID messageId,
    UUID noticeId,
    ReportReason reason,
    String detail,
    ReviewStatus reviewStatus,
    OffsetDateTime reportedAt,
    Message message,
    UUID reviewedBy,
    OffsetDateTime reviewedAt) {

  /**
   * @param reportCount 검토 전 신고 수
   */
  public record Message(
      String authorNickname, String content, MessageStatus status, int reportCount) {}

  /**
   * 관리자 사이드바 숫자.
   *
   * @param pendingMessages 검토 전 신고가 걸린 글 수 (같은 글의 신고 여러 건은 한 글)
   */
  public record Counts(int pendingMessages) {}
}
