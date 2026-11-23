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
public class EmailDeliveryController
    implements kr.mujuthaek.api.user.controller.spec.EmailDeliveryApiSpec {
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

  public record Check(UUID userId, String email, String type) {}

  public record Token(String token) {
    @Override
    public String toString() {
      return "EmailToken[REDACTED]";
    }
  }

  @PostMapping("/internal/email-eligibility")
  public EmailNotificationService.Eligibility eligible(
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

  @Override
  @PostMapping("/api/email-notifications/verify")
  @ResponseStatus(org.springframework.http.HttpStatus.NO_CONTENT)
  public void verify(@RequestBody Token body) {
    emails.verifyLink(body.token());
  }

  @PostMapping("/api/email-notifications/unsubscribe")
  public void unsubscribe(@RequestBody Token body) {
    emails.unsubscribe(body.token());
  }

  /**
   * 메일 앱의 「수신 거부」 버튼(RFC 8058 {@code List-Unsubscribe-Post}). 메일 앱은 머리글의 주소에 {@code
   * List-Unsubscribe=One-Click} 폼을 POST할 뿐이라 서명된 토큰을 주소에 실어요. 위 링크 해제와 같은 검사를 해요(2026-11-16 보안 감사
   * 4장).
   */
  @PostMapping("/api/email-notifications/unsubscribe/one-click")
  public void unsubscribeOneClick(@RequestParam("token") String token) {
    emails.unsubscribe(token);
  }
}
