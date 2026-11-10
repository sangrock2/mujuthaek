package kr.mujuthaek.api.notification.controller;

import java.util.UUID;
import kr.mujuthaek.api.notification.controller.spec.NotificationEventApiSpec;
import kr.mujuthaek.api.notification.service.internal.InboxService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

/** 알림을 봤는지·눌렀는지 알려 받기 (설명은 {@link NotificationEventApiSpec}). */
@RestController
class NotificationEventController implements NotificationEventApiSpec {

  private final InboxService inbox;

  NotificationEventController(InboxService inbox) {
    this.inbox = inbox;
  }

  @Override
  @PostMapping("/api/v1/notifications/{id}/shown")
  public ResponseEntity<Void> shown(@PathVariable UUID id) {
    inbox.markShown(id);
    return ResponseEntity.noContent().build();
  }

  @Override
  @PostMapping("/api/v1/notifications/{id}/clicked")
  public ResponseEntity<Void> clicked(@PathVariable UUID id) {
    inbox.markClicked(id);
    return ResponseEntity.noContent().build();
  }
}
