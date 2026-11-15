package kr.mujuthaek.notification.delivery.email;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import kr.mujuthaek.notification.delivery.DeliveryException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/** api가 생성한 인증 토큰만 전송해요. log 모드에서는 인증 링크를 기록하지 않아요. */
@RestController
class EmailVerificationController {
  private final EmailSender sender;
  private final MailProperties properties;
  private final String secret;

  EmailVerificationController(
      EmailSender sender,
      MailProperties properties,
      @Value("${notification.internal.token:}") String secret) {
    this.sender = sender;
    this.properties = properties;
    this.secret = secret;
  }

  record Request(String email, String token) {
    @Override
    public String toString() {
      return "EmailVerification[REDACTED]";
    }
  }

  @PostMapping("/internal/email-verification")
  ResponseEntity<Void> send(
      @RequestHeader(value = "Authorization", defaultValue = "") String authorization,
      @RequestBody Request body) {
    if (secret.isBlank()
        || !MessageDigest.isEqual(
            ("Bearer " + secret).getBytes(StandardCharsets.UTF_8),
            authorization.getBytes(StandardCharsets.UTF_8))) {
      return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
    }
    if (!"ses".equals(properties.provider()))
      return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
    if (body.email() == null
        || body.email().length() > 254
        || !body.email().matches("[^\\s\\p{Cc}@]+@[^\\s\\p{Cc}@]+\\.[^\\s\\p{Cc}@]+")
        || body.token() == null
        || !body.token().matches("[a-f0-9]{64}")) return ResponseEntity.badRequest().build();
    String link = properties.webBaseUrl() + "/email/verify#token=" + body.token();
    try {
      sender.send(
          new EmailMessage(
              body.email(),
              "[무주택자들] 알림 이메일 주소 인증",
              "이메일 알림을 신청하셨다면 아래 링크에서 주소 인증을 완료해 주세요.\n\n"
                  + link
                  + "\n\n링크는 15분 동안 한 번만 사용할 수 있어요. 인증 후 수신 동의를 해야 알림이 켜져요."
                  + "\n직접 요청하지 않았다면 이 메일을 무시해 주세요.\n문의: contact@mujuthaek.store"));
      return ResponseEntity.noContent().build();
    } catch (DeliveryException e) {
      return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
    }
  }
}
