package kr.mujuthaek.api.chat.mapper;

import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.UUID;
import kr.mujuthaek.api.chat.domain.MessageStatus;
import kr.mujuthaek.api.chat.dto.response.ChatMessageResponse;
import kr.mujuthaek.api.chat.dto.response.ChatReportResponse;
import kr.mujuthaek.api.chat.repository.ChatMessageRepository.MessageRow;
import kr.mujuthaek.api.chat.repository.ChatReportRepository.ReportRow;

/** 저장한 메시지·신고 → 응답. 삭제·가린 메시지는 본문을 내보내지 않아요. */
public final class ChatMessageMapper {

  /** 답장 미리보기 길이 (글자). */
  static final int PREVIEW_LENGTH = 50;

  private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");

  private ChatMessageMapper() {}

  /**
   * @param viewer 보는 회원 (내 글 여부용). 비로그인·SSE로 보내는 메시지는 null
   */
  public static ChatMessageResponse toResponse(MessageRow row, UUID viewer) {
    return new ChatMessageResponse(
        row.id(),
        row.noticeId(),
        row.authorNickname(),
        row.status() == MessageStatus.VISIBLE ? row.content() : null,
        row.status(),
        row.likeCount(),
        row.likedByViewer(),
        viewer != null && viewer.equals(row.userId()),
        row.parentId() == null ? null : parent(row),
        seoul(row.createdAt()));
  }

  /** 답장 원문 미리보기. 원문이 작성자 탈퇴로 지워져 줄이 없으면 지운 글처럼 보여줘요. */
  private static ChatMessageResponse.Parent parent(MessageRow row) {
    if (row.parentStatus() == null) {
      return new ChatMessageResponse.Parent(row.parentId(), null, null, MessageStatus.DELETED);
    }
    return new ChatMessageResponse.Parent(
        row.parentId(),
        row.parentNickname(),
        row.parentStatus() == MessageStatus.VISIBLE ? preview(row.parentContent()) : null,
        row.parentStatus());
  }

  public static ChatReportResponse toResponse(ReportRow row) {
    return new ChatReportResponse(
        row.id(),
        row.messageId(),
        row.noticeId(),
        row.reason(),
        row.detail(),
        row.reviewStatus(),
        seoul(row.createdAt()),
        new ChatReportResponse.Message(
            row.authorNickname(), row.content(), row.messageStatus(), row.reportCount()),
        row.reviewedBy(),
        row.reviewedAt() == null ? null : seoul(row.reviewedAt()));
  }

  private static String preview(String content) {
    if (content == null || content.codePointCount(0, content.length()) <= PREVIEW_LENGTH) {
      return content;
    }
    return content.substring(0, content.offsetByCodePoints(0, PREVIEW_LENGTH));
  }

  private static OffsetDateTime seoul(OffsetDateTime at) {
    return at.atZoneSameInstant(SEOUL).toOffsetDateTime();
  }
}
