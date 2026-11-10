package kr.mujuthaek.api.notification.controller;

import java.util.UUID;
import kr.mujuthaek.api.common.dto.response.CursorPageResponse;
import kr.mujuthaek.api.notification.controller.spec.NotificationInboxApiSpec;
import kr.mujuthaek.api.notification.dto.response.NotificationItemResponse;
import kr.mujuthaek.api.notification.dto.response.UnreadCountResponse;
import kr.mujuthaek.api.notification.service.internal.InboxService;
import kr.mujuthaek.api.user.service.LoginUser;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 알림함 (설명은 {@link NotificationInboxApiSpec}). */
@RestController
@RequestMapping("/api/users/me/notifications")
class NotificationInboxController implements NotificationInboxApiSpec {

  private final InboxService inbox;

  NotificationInboxController(InboxService inbox) {
    this.inbox = inbox;
  }

  @Override
  @GetMapping
  public CursorPageResponse<NotificationItemResponse> list(
      @AuthenticationPrincipal LoginUser user,
      @RequestParam(required = false) String cursor,
      @RequestParam(required = false) Integer size,
      @RequestParam(defaultValue = "false") boolean unread) {
    return inbox.list(user.userId(), cursor, size, unread);
  }

  @Override
  @GetMapping("/unread-count")
  public UnreadCountResponse unreadCount(@AuthenticationPrincipal LoginUser user) {
    return new UnreadCountResponse(inbox.unreadCount(user.userId()));
  }

  @Override
  @PostMapping("/{id}/read")
  public ResponseEntity<Void> markRead(
      @AuthenticationPrincipal LoginUser user, @PathVariable UUID id) {
    inbox.markRead(user.userId(), id);
    return ResponseEntity.noContent().build();
  }

  @Override
  @PostMapping("/read-all")
  public ResponseEntity<Void> markAllRead(@AuthenticationPrincipal LoginUser user) {
    inbox.markAllRead(user.userId());
    return ResponseEntity.noContent().build();
  }
}
