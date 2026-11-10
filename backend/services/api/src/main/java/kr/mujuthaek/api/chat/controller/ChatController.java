package kr.mujuthaek.api.chat.controller;

import jakarta.validation.Valid;
import java.util.UUID;
import kr.mujuthaek.api.chat.controller.spec.ChatApiSpec;
import kr.mujuthaek.api.chat.dto.request.ReportRequest;
import kr.mujuthaek.api.chat.dto.request.SendMessageRequest;
import kr.mujuthaek.api.chat.dto.response.ChatMessageResponse;
import kr.mujuthaek.api.chat.dto.response.ChatRoomResponse;
import kr.mujuthaek.api.chat.dto.response.LikeResponse;
import kr.mujuthaek.api.chat.service.ChatService;
import kr.mujuthaek.api.common.dto.response.CursorPageResponse;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.user.service.LoginUser;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * 공고 채팅 (설명은 {@link ChatApiSpec}). 시큐리티가 이 경로들을 열어 두어서(permitAll) 쓰기는 여기서 로그인을 확인해 401
 * UNAUTHENTICATED를 내요.
 */
@RestController
@RequestMapping("/api/v1")
class ChatController implements ChatApiSpec {

  private final ChatService chats;

  ChatController(ChatService chats) {
    this.chats = chats;
  }

  @Override
  @GetMapping("/notices/{noticeId}/chat")
  public ChatRoomResponse room(@PathVariable UUID noticeId) {
    return chats.room(noticeId);
  }

  @Override
  @GetMapping("/notices/{noticeId}/chat/messages")
  public CursorPageResponse<ChatMessageResponse> messages(
      @PathVariable UUID noticeId,
      @RequestParam(required = false) String cursor,
      @RequestParam(required = false) Integer size,
      @AuthenticationPrincipal LoginUser user) {
    return chats.messages(noticeId, cursor, size, user == null ? null : user.userId());
  }

  @Override
  @PostMapping("/notices/{noticeId}/chat/messages")
  public ResponseEntity<ChatMessageResponse> send(
      @PathVariable UUID noticeId,
      @RequestBody SendMessageRequest request,
      @AuthenticationPrincipal LoginUser user) {
    UUID userId = loggedIn(user);
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(chats.send(noticeId, userId, user.nickname(), request));
  }

  @Override
  @DeleteMapping("/chat/messages/{id}")
  public ResponseEntity<Void> delete(
      @PathVariable UUID id, @AuthenticationPrincipal LoginUser user) {
    chats.delete(id, loggedIn(user));
    return ResponseEntity.noContent().build();
  }

  @Override
  @PutMapping("/chat/messages/{id}/like")
  public LikeResponse like(@PathVariable UUID id, @AuthenticationPrincipal LoginUser user) {
    return chats.like(id, loggedIn(user));
  }

  @Override
  @DeleteMapping("/chat/messages/{id}/like")
  public LikeResponse unlike(@PathVariable UUID id, @AuthenticationPrincipal LoginUser user) {
    return chats.unlike(id, loggedIn(user));
  }

  @Override
  @PostMapping("/chat/messages/{id}/reports")
  public ResponseEntity<Void> report(
      @PathVariable UUID id,
      @Valid @RequestBody ReportRequest request,
      @AuthenticationPrincipal LoginUser user) {
    chats.report(id, loggedIn(user), request);
    return ResponseEntity.status(HttpStatus.CREATED).build();
  }

  @Override
  @GetMapping(
      value = "/notices/{noticeId}/chat/stream",
      produces = MediaType.TEXT_EVENT_STREAM_VALUE)
  public SseEmitter stream(
      @PathVariable UUID noticeId,
      @RequestHeader(name = "Last-Event-ID", required = false) String lastEventId) {
    return chats.subscribe(noticeId, lastEventId);
  }

  private static UUID loggedIn(LoginUser user) {
    if (user == null) {
      throw new CustomException(ErrorCode.UNAUTHENTICATED);
    }
    return user.userId();
  }
}
