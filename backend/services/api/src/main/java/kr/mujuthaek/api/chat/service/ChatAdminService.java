package kr.mujuthaek.api.chat.service;

import java.time.Clock;
import java.time.OffsetDateTime;
import java.util.UUID;
import kr.mujuthaek.api.chat.domain.MessageStatus;
import kr.mujuthaek.api.chat.domain.ReviewAction;
import kr.mujuthaek.api.chat.domain.ReviewStatus;
import kr.mujuthaek.api.chat.dto.response.ChatReportResponse;
import kr.mujuthaek.api.chat.event.ChatEvent;
import kr.mujuthaek.api.chat.mapper.ChatMessageMapper;
import kr.mujuthaek.api.chat.repository.ChatMessageRepository;
import kr.mujuthaek.api.chat.repository.ChatMessageRepository.MessageRow;
import kr.mujuthaek.api.chat.repository.ChatReportRepository;
import kr.mujuthaek.api.common.dto.response.CursorPageResponse;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.common.pagination.CursorKey;
import kr.mujuthaek.api.common.pagination.CursorQuery;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 관리자의 채팅 신고 검토: 신고 목록과 가림 유지·다시 보이기. */
@Service
public class ChatAdminService {

  private static final String SORT = "LATEST";

  private final ChatMessageRepository messages;
  private final ChatReportRepository reports;
  private final ApplicationEventPublisher events;
  private final Clock clock;

  public ChatAdminService(
      ChatMessageRepository messages,
      ChatReportRepository reports,
      ApplicationEventPublisher events,
      Clock clock) {
    this.messages = messages;
    this.reports = reports;
    this.events = events;
    this.clock = clock;
  }

  /** 검토 상태별 신고 (최신순). */
  /** 검토 전 신고가 걸린 글 수 (사이드바 숫자). 신고 목록을 받아 세지 않게 따로 세요. */
  public ChatReportResponse.Counts counts() {
    return new ChatReportResponse.Counts(reports.pendingMessages());
  }

  public CursorPageResponse<ChatReportResponse> reports(
      ReviewStatus status, String cursor, Integer size) {
    CursorQuery query = CursorQuery.of(cursor, size, SORT);
    UUID before = query.after() == null ? null : query.after().id();
    return CursorPageResponse.from(
        reports.page(status, before, query.fetchSize()),
        query.size(),
        ChatMessageMapper::toResponse,
        row -> CursorKey.of(SORT, null, row.id()));
  }

  /**
   * 신고된 메시지 처리. 그 메시지의 검토 전 신고가 모두 처리 결과로 바뀌어요.
   *
   * <ul>
   *   <li>KEEP_HIDDEN: 관리자 가림(HIDDEN_ADMIN). 보이던 메시지면 SSE로 message.hidden
   *   <li>RESTORE: 다시 보이게(VISIBLE), 검토 전 신고 수 0. 가려져 있었으면 SSE로 message.restored
   * </ul>
   *
   * 작성자가 지운 메시지는 신고만 처리 결과로 닫고 상태는 DELETED 그대로 둬요 (지운 글을 다시 보이게 하지 않아요). 신고된 뒤 지운 글도 검토 목록에서 닫을 수
   * 있게요. 처리한 관리자와 시각을 신고 줄에 남겨요 (관리자 「처리 기록」).
   *
   * @param reviewer 처리한 관리자 회원 ID
   */
  @Transactional
  public void review(UUID messageId, ReviewAction action, UUID reviewer) {
    OffsetDateTime now = OffsetDateTime.now(clock);
    MessageRow row =
        messages
            .find(messageId, null)
            .orElseThrow(() -> new CustomException(ErrorCode.CHAT_MESSAGE_NOT_FOUND));
    if (row.status() == MessageStatus.DELETED) {
      reports.review(
          messageId,
          action == ReviewAction.KEEP_HIDDEN ? ReviewStatus.KEPT_HIDDEN : ReviewStatus.RESTORED,
          reviewer,
          now);
      return;
    }
    switch (action) {
      case KEEP_HIDDEN -> {
        messages.review(messageId, MessageStatus.HIDDEN_ADMIN, false);
        reports.review(messageId, ReviewStatus.KEPT_HIDDEN, reviewer, now);
        if (row.status() == MessageStatus.VISIBLE) {
          events.publishEvent(ChatEvent.hidden(row.noticeId(), messageId));
        }
      }
      case RESTORE -> {
        messages.review(messageId, MessageStatus.VISIBLE, true);
        reports.review(messageId, ReviewStatus.RESTORED, reviewer, now);
        if (row.status().hidden()) {
          MessageRow restored = messages.find(messageId, null).orElseThrow();
          events.publishEvent(ChatEvent.restored(ChatMessageMapper.toResponse(restored, null)));
        }
      }
    }
  }
}
