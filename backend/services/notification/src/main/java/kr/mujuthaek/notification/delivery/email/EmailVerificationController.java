package kr.mujuthaek.notification.delivery.email;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.regex.Pattern;
import kr.mujuthaek.notification.delivery.DeliveryException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * api가 생성한 인증 정보만 전송해요. log 모드에서는 인증번호나 링크를 기록하지 않아요. 받는 주소별·전체 상한을 넘으면 보내지 않아요(429, {@link
 * VerificationMailLimiter}).
 */
@RestController
class EmailVerificationController {
  /**
   * 아이디@도메인.최상위. 공백·제어 문자와 {@code <>()[]\,;:"}는 안 돼요. 표시 이름 형식(「이름&lt;남@x.com&gt;」)으로 주소별 상한을 피하거나
   * 받는 사람 이름을 꾸미지 못하게 해요(api ContactEmailService와 같은 규칙).
   */
  private static final Pattern EMAIL =
      Pattern.compile(
          "[^\\s\\p{Cc}@<>()\\[\\]\\\\,;:\"]+@[^\\s\\p{Cc}@<>()\\[\\]\\\\,;:\"]+"
              + "\\.[^\\s\\p{Cc}@<>()\\[\\]\\\\,;:\"]+");

  private final EmailSender sender;
  private final MailProperties properties;
  private final VerificationMailLimiter limiter;
  private final String secret;

  EmailVerificationController(
      EmailSender sender,
      MailProperties properties,
      VerificationMailLimiter limiter,
      @Value("${notification.internal.token:}") String secret) {
    this.sender = sender;
    this.properties = properties;
    this.limiter = limiter;
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
        || !EMAIL.matcher(body.email()).matches()
        || body.token() == null
        || !body.token().matches("[0-9]{6}|[a-f0-9]{64}"))
      return ResponseEntity.badRequest().build();
    if (!limiter.tryAcquire(body.email())) {
      return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS).build();
    }
    boolean code = body.token().length() == 6;
    String instructions =
        code
            ? "알림 설정에 아래 인증번호를 입력해 주세요.\n\n" + body.token() + "\n\n인증번호는 발급 후 5분 동안 한 번만 사용할 수 있어요."
            : "이메일 알림을 신청하셨다면 아래 링크에서 주소 인증을 완료해 주세요.\n\n"
                + properties.webBaseUrl()
                + "/email/verify#token="
                + body.token()
                + "\n\n링크는 15분 동안 한 번만 사용할 수 있어요. 인증 후 수신 동의를 해야 알림이 켜져요.";
    try {
      sender.send(
          new EmailMessage(
              body.email(),
              code ? "[무주택자들] 알림 이메일 인증번호" : "[무주택자들] 알림 이메일 주소 인증",
              instructions + "\n직접 요청하지 않았다면 이 메일을 무시해 주세요.\n문의: contact@mujuthaek.store"));
      return ResponseEntity.noContent().build();
    } catch (DeliveryException e) {
      return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
    }
  }
}
