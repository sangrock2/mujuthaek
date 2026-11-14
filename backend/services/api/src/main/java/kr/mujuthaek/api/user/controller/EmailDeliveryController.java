package kr.mujuthaek.api.user.controller;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.UUID;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.user.service.EmailNotificationService;
import kr.mujuthaek.api.user.service.NotificationPreference;
import kr.mujuthaek.api.user.service.UserNotificationQueryService;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.*;

/** 발송 직전 동의를 다시 봐서, 수신 해제 전에 큐에 들어간 메일도 차단해요. */
@RestController
class EmailDeliveryController {
  private final EmailNotificationService emails;
  private final String secret;
  private final UserNotificationQueryService users;

  EmailDeliveryController(
      EmailNotificationService emails,
      UserNotificationQueryService users,
      @Value("${mujuthaek.notification.server.token:}") String secret) {
    this.emails = emails;
    this.secret = secret;
    this.users = users;
  }

  record Check(UUID userId, String email, String type) {}

  record Token(String token) {
    @Override
    public String toString() {
      return "UnsubscribeToken[REDACTED]";
    }
  }

  @PostMapping("/internal/email-eligibility")
  EmailNotificationService.Eligibility eligible(
      @RequestHeader(value = "X-Notification-Token", defaultValue = "") String token,
      @RequestBody Check body) {
    if (secret.isBlank()
        || !MessageDigest.isEqual(
            secret.getBytes(StandardCharsets.UTF_8), token.getBytes(StandardCharsets.UTF_8))) {
      throw new CustomException(ErrorCode.FORBIDDEN);
    }
    if (body.userId() == null || body.email() == null || body.type() == null)
      throw new CustomException(ErrorCode.VALIDATION_FAILED);
    if (!users
        .preferences(java.util.List.of(body.userId()))
        .getOrDefault(body.userId(), NotificationPreference.DEFAULT)
        .enabled(body.type())) {
      return new EmailNotificationService.Eligibility(false, null);
    }
    return emails.eligible(body.userId(), body.email(), body.type());
  }

  @PostMapping("/api/email-notifications/unsubscribe")
  void unsubscribe(@RequestBody Token body) {
    emails.unsubscribe(body.token());
  }
}
