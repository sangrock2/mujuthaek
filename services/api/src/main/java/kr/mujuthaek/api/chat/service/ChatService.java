package kr.mujuthaek.api.chat.service;

import java.time.Clock;
import java.time.Duration;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.UUID;
import java.util.function.Supplier;
import kr.mujuthaek.api.chat.domain.ChatRoom;
import kr.mujuthaek.api.chat.domain.MessageStatus;
import kr.mujuthaek.api.chat.domain.PersonalInfo;
import kr.mujuthaek.api.chat.dto.request.ReportRequest;
import kr.mujuthaek.api.chat.dto.request.SendMessageRequest;
import kr.mujuthaek.api.chat.dto.response.ChatMessageResponse;
import kr.mujuthaek.api.chat.dto.response.ChatRoomResponse;
import kr.mujuthaek.api.chat.dto.response.LikeResponse;
import kr.mujuthaek.api.chat.event.ChatEvent;
import kr.mujuthaek.api.chat.mapper.ChatMessageMapper;
import kr.mujuthaek.api.chat.repository.ChatMessageRepository;
import kr.mujuthaek.api.chat.repository.ChatMessageRepository.MessageRow;
import kr.mujuthaek.api.chat.repository.ChatReportRepository;
import kr.mujuthaek.api.common.dto.response.CursorPageResponse;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.common.id.UuidV7;
import kr.mujuthaek.api.common.pagination.CursorKey;
import kr.mujuthaek.api.common.pagination.CursorQuery;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * 공고 채팅: 읽기(방 정보·목록·SSE)는 누구나, 쓰기(보내기·삭제·좋아요·신고)는 로그인한 회원만. 쓰기는 커밋된 뒤에만 SSE로 퍼져요({@link
 * ChatEvent}).
 */
@Service
public class ChatService {

  static final int MAX_LENGTH = 500;
  static final int SEND_LIMIT = 5;
  static final Duration SEND_WINDOW = Duration.ofMinutes(1);
  static final int REPORTS_TO_HIDE = 3;
  static final int DEFAULT_PAGE_SIZE = 30;

  /** 재연결 때 한 번에 다시 보낼 놓친 메시지 수. 더 놓쳤으면 화면이 목록을 다시 불러 맞춰요. */
  static final int RESUME_LIMIT = 100;

  static final String GUIDE = "채팅은 사용자 의견이에요. 판정 결과가 아니니 지원 자격은 공고문과 판정 결과로 확인해 주세요.";

  private static final String SORT = "LATEST";

  private final ChatRooms rooms;
  private final ChatMessageRepository messages;
  private final ChatReportRepository reports;
  private final ChatSseHub hub;
  private final ApplicationEventPublisher events;
  private final Clock clock;

  public ChatService(
      ChatRooms rooms,
      ChatMessageRepository messages,
      ChatReportRepository reports,
      ChatSseHub hub,
      ApplicationEventPublisher events,
      Clock clock) {
    this.rooms = rooms;
    this.messages = messages;
    this.reports = reports;
    this.hub = hub;
    this.events = events;
    this.clock = clock;
  }

  public ChatRoomResponse room(UUID noticeId) {
    ChatRoom room = findRoom(noticeId);
    return new ChatRoomResponse(
        room.noticeId(), room.readOnly(today()), room.readOnlyFrom(), GUIDE);
  }

  /**
   * 메시지 목록 (최신순, 기본 30개). 답장도 같은 목록에 시간순으로 섞여요.
   *
   * @param viewer 로그인한 회원 (내 좋아요·내 글 여부). 비로그인이면 null
   */
  public CursorPageResponse<ChatMessageResponse> messages(
      UUID noticeId, String cursor, Integer size, UUID viewer) {
    ChatRoom room = findRoom(noticeId);
    CursorQuery query = CursorQuery.of(cursor, size == null ? DEFAULT_PAGE_SIZE : size, SORT);
    UUID before = query.after() == null ? null : query.after().id();
    return CursorPageResponse.from(
        messages.page(room.noticeIds(), before, query.fetchSize(), viewer), // 합쳐진 공고의 메시지도
        query.size(),
        row -> ChatMessageMapper.toResponse(row, viewer),
        row -> CursorKey.of(SORT, null, row.id()));
  }

  /**
   * 보내기·답장. 순서: 방 → 읽기 전용 → 본문 → 답장 대상 → 1분 5개.
   *
   * @param nickname 보낼 때의 닉네임 (메시지에 함께 저장해요)
   */
  @Transactional
  public ChatMessageResponse send(
      UUID noticeId, UUID userId, String nickname, SendMessageRequest request) {
    ChatRoom room = findRoom(noticeId);
    requireWritable(room);
    String content = checkedContent(request.content());
    if (request.parentId() != null) {
      MessageRow parent =
          messages
              .find(request.parentId(), null)
              .filter(p -> room.noticeIds().contains(p.noticeId())) // 합치기 전 메시지에도 답장
              .filter(p -> p.status() == MessageStatus.VISIBLE)
              .orElseThrow(messageNotFound());
      if (parent.parentId() != null) {
        throw new CustomException(ErrorCode.CHAT_REPLY_DEPTH);
      }
    }
    OffsetDateTime now = now();
    messages.lockSender(userId);
    var recent = messages.recentSends(userId, now.minus(SEND_WINDOW));
    if (recent.count() >= SEND_LIMIT) {
      long wait = Duration.between(now, recent.oldest().plus(SEND_WINDOW)).toSeconds() + 1;
      throw new ChatRateLimitedException(Math.clamp(wait, 1, SEND_WINDOW.toSeconds()));
    }
    UUID id = UuidV7.next();
    messages.insert(id, room.noticeId(), userId, nickname, request.parentId(), content, now);
    MessageRow saved = messages.find(id, userId).orElseThrow();
    events.publishEvent(ChatEvent.created(ChatMessageMapper.toResponse(saved, null)));
    return ChatMessageMapper.toResponse(saved, userId);
  }

  /** 내 글 삭제 (읽기 전용 방에서도 돼요). 소프트 삭제라 화면에서는 내려가고 본문은 부적절한 글 신고 검토용으로 DB에 남아요. 이미 지운 글이면 그대로 둬요. */
  @Transactional
  public void delete(UUID messageId, UUID userId) {
    MessageRow row = messages.find(messageId, null).orElseThrow(messageNotFound());
    if (!userId.equals(row.userId())) {
      throw new CustomException(ErrorCode.CHAT_NOT_OWNER);
    }
    if (messages.markDeleted(messageId, now())) {
      events.publishEvent(ChatEvent.deleted(row.noticeId(), messageId));
    }
  }

  /** 좋아요. 여러 번 불러도 결과가 같아요. 보이는 메시지만, 읽기 전용 방은 409. */
  @Transactional
  public LikeResponse like(UUID messageId, UUID userId) {
    MessageRow row =
        messages
            .find(messageId, null)
            .filter(m -> m.status() == MessageStatus.VISIBLE)
            .orElseThrow(messageNotFound());
    requireWritable(findRoom(row.noticeId()));
    if (!messages.addLike(messageId, userId, now())) {
      return new LikeResponse(messageId, row.likeCount(), true);
    }
    int count = messages.addLikeCount(messageId, 1);
    events.publishEvent(ChatEvent.likeUpdated(row.noticeId(), messageId, count));
    return new LikeResponse(messageId, count, true);
  }

  /** 좋아요 취소. 여러 번 불러도 결과가 같아요. 읽기 전용 방은 409. */
  @Transactional
  public LikeResponse unlike(UUID messageId, UUID userId) {
    MessageRow row = messages.find(messageId, null).orElseThrow(messageNotFound());
    requireWritable(findRoom(row.noticeId()));
    if (!messages.removeLike(messageId, userId)) {
      return new LikeResponse(messageId, row.likeCount(), false);
    }
    int count = messages.addLikeCount(messageId, -1);
    events.publishEvent(ChatEvent.likeUpdated(row.noticeId(), messageId, count));
    return new LikeResponse(messageId, count, false);
  }

  /** 신고 (읽기 전용 방에서도 돼요). 검토 전 신고 3건째에 자동으로 가리고 관리자 검토를 기다려요. 같은 회원이 두 번 신고하면 409. */
  @Transactional
  public void report(UUID messageId, UUID userId, ReportRequest request) {
    MessageRow row =
        messages
            .find(messageId, null)
            .filter(m -> m.status() != MessageStatus.DELETED)
            .orElseThrow(messageNotFound());
    if (!reports.insert(
        UuidV7.next(), messageId, userId, request.reason(), request.detail(), now())) {
      throw new CustomException(ErrorCode.CHAT_ALREADY_REPORTED);
    }
    MessageStatus after = messages.countReport(messageId, REPORTS_TO_HIDE);
    if (row.status() == MessageStatus.VISIBLE && after == MessageStatus.HIDDEN_REPORTED) {
      events.publishEvent(ChatEvent.hidden(row.noticeId(), messageId));
    }
  }

  /**
   * SSE 구독. 합쳐진 공고 ID로 와도 남은 공고의 방에 붙어요.
   *
   * @param lastEventId 재연결이면 브라우저가 보낸 마지막 메시지 ID. 그 뒤 메시지를 먼저 보내요 (읽을 수 없는 값이면 무시)
   */
  public SseEmitter subscribe(UUID noticeId, String lastEventId) {
    ChatRoom room = findRoom(noticeId);
    SseEmitter emitter = hub.subscribe(room.noticeId());
    UUID after = eventId(lastEventId);
    if (after != null) {
      for (MessageRow row : messages.after(room.noticeIds(), after, RESUME_LIMIT)) {
        hub.send(emitter, ChatEvent.created(ChatMessageMapper.toResponse(row, null)));
      }
    }
    return emitter;
  }

  /**
   * 탈퇴한 회원의 채팅 데이터 줄을 지워요 (요구사항 3-16: 탈퇴 후 데이터 0건). 보고 있는 사람 화면에서도 내려가게 지운 메시지를 방송해요(방송은 커밋 뒤). 탈퇴
   * 트랜잭션에 함께 들어가요(커밋 직전에 불림, notice·area 제보 지우기와 같아요).
   */
  @Transactional
  public void forget(UUID userId) {
    for (var message : messages.forget(userId)) {
      events.publishEvent(ChatEvent.deleted(message.noticeId(), message.id()));
    }
  }

  private ChatRoom findRoom(UUID noticeId) {
    return rooms.find(noticeId).orElseThrow(() -> new CustomException(ErrorCode.NOTICE_NOT_FOUND));
  }

  private void requireWritable(ChatRoom room) {
    if (room.readOnly(today())) {
      throw new CustomException(ErrorCode.CHAT_READ_ONLY);
    }
  }

  /** 앞뒤 공백을 지우고 1~500자인지 봐요 (글자 수는 이모지도 한 글자). */
  private static String checkedContent(String content) {
    String stripped = content == null ? "" : content.strip();
    int length = stripped.codePointCount(0, stripped.length());
    if (length == 0 || length > MAX_LENGTH) {
      throw new CustomException(ErrorCode.CHAT_INVALID_CONTENT);
    }
    if (PersonalInfo.contains(stripped)) {
      throw new CustomException(ErrorCode.CHAT_PERSONAL_INFO);
    }
    return stripped;
  }

  private static UUID eventId(String value) {
    if (value == null || value.isBlank()) {
      return null;
    }
    try {
      return UUID.fromString(value.strip());
    } catch (IllegalArgumentException e) {
      return null;
    }
  }

  private static Supplier<CustomException> messageNotFound() {
    return () -> new CustomException(ErrorCode.CHAT_MESSAGE_NOT_FOUND);
  }

  private OffsetDateTime now() {
    return OffsetDateTime.now(clock);
  }

  private LocalDate today() {
    return LocalDate.now(clock);
  }
}
