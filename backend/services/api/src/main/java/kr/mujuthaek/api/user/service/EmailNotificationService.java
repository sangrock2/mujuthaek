package kr.mujuthaek.api.user.service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.ZoneId;
import java.util.Collection;
import java.util.HexFormat;
import java.util.Map;
import java.util.UUID;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.user.repository.NotificationEmailRepository;
import kr.mujuthaek.api.user.repository.NotificationEmailRepository.Saved;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.RestClientException;

/** 연락용 이메일과 별도 동의. 인증·수신 동의가 모두 있어야 알림 주소를 반환해요. */
@Service
public class EmailNotificationService {
  private static final SecureRandom RANDOM = new SecureRandom();
  private final NotificationEmailRepository emails;
  private final EmailVerificationSender mail;
  private final Clock clock;
  private final String secret;

  public EmailNotificationService(
      NotificationEmailRepository emails,
      EmailVerificationSender mail,
      Clock clock,
      @Value("${mujuthaek.notification.server.token:}") String secret) {
    this.emails = emails;
    this.mail = mail;
    this.clock = clock;
    this.secret = secret;
  }

  public record Status(
      String email,
      boolean verified,
      boolean enabled,
      boolean newNotice,
      boolean deadline,
      boolean reportAnswer) {}

  public record Settings(
      boolean enabled,
      boolean newNotice,
      boolean deadline,
      boolean reportAnswer,
      boolean consent) {}

  @Transactional(readOnly = true)
  public Status get(UUID id) {
    return emails
        .find(id)
        .map(this::status)
        .orElse(new Status(null, false, false, false, false, false));
  }

  @Transactional
  public Status request(UUID id, String input) {
    String address = ContactEmailService.normalize(input);
    emails.lock(id);
    var now = clock.instant();
    var day = now.atZone(ZoneId.of("Asia/Seoul")).toLocalDate();
    Saved previous = emails.find(id).orElse(null);
    int count = previous != null && day.equals(previous.requestDay()) ? previous.requestCount() : 0;
    if (count >= 5 || previous != null && previous.requestedAt().plusSeconds(60).isAfter(now)) {
      throw new CustomException(ErrorCode.RATE_LIMITED);
    }
    String token = randomToken();
    emails.request(id, address, hash(token), randomToken(), now, day, count + 1);
    try {
      mail.sendEmailVerification(address, token);
    } catch (RestClientException e) {
      throw new CustomException(ErrorCode.EMAIL_DELIVERY_UNAVAILABLE);
    }
    return get(id);
  }

  @Transactional
  public Status verify(UUID id, String token) {
    emails.lock(id);
    Saved saved = emails.find(id).orElseThrow(EmailNotificationService::invalid);
    if (token == null
        || !token.matches("[a-f0-9]{64}")
        || saved.tokenHash() == null
        || saved.expiresAt() == null
        || !saved.expiresAt().isAfter(clock.instant())
        || !equal(saved.tokenHash(), hash(token))) throw invalid();
    emails.verify(id, clock.instant());
    return get(id);
  }

  @Transactional
  public Status save(UUID id, Settings s) {
    emails.lock(id);
    Saved saved = emails.find(id).orElseThrow(EmailNotificationService::invalid);
    if (s.enabled() && (saved.verifiedAt() == null || !s.consent())) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "인증된 이메일과 수신 동의가 필요해요");
    }
    emails.settings(
        id, s.enabled(), s.newNotice(), s.deadline(), s.reportAnswer(), clock.instant());
    return get(id);
  }

  @Transactional
  public void remove(UUID id) {
    emails.lock(id);
    emails.delete(id);
  }

  @org.springframework.scheduling.annotation.Scheduled(fixedDelay = 3600000)
  @Transactional
  public void expirePending() {
    emails.expirePending(clock.instant().minusSeconds(86400));
  }

  public record EmailRecipient(
      String email,
      boolean enabled,
      boolean verified,
      boolean newNotice,
      boolean deadline,
      boolean reportAnswer) {
    public boolean allows(String type) {
      return enabled
          && verified
          && switch (type) {
            case "NEW_NOTICE", "NEW_SUPPORT" -> newNotice;
            case "DEADLINE_D3", "DEADLINE_D1" -> deadline;
            case "REPORT_ANSWERED" -> reportAnswer;
            default -> false;
          };
    }

    @Override
    public String toString() {
      return "EmailRecipient[REDACTED]";
    }
  }

  @Transactional(readOnly = true)
  public Map<UUID, EmailRecipient> recipients(Collection<UUID> ids) {
    Map<UUID, EmailRecipient> out = new java.util.HashMap<>();
    emails
        .findAll(ids)
        .forEach(
            (id, s) ->
                out.put(
                    id,
                    new EmailRecipient(
                        s.email(),
                        s.enabled(),
                        s.verifiedAt() != null,
                        s.newNotice(),
                        s.deadline(),
                        s.reportAnswer())));
    return out;
  }

  @Transactional(readOnly = true)
  public java.util.List<UUID> preparing(UUID noticeId) {
    return emails.preparing(noticeId);
  }

  public record Eligibility(boolean allowed, String unsubscribeToken) {}

  @Transactional(readOnly = true)
  public Eligibility eligible(UUID id, String address, String type) {
    return emails
        .find(id)
        .filter(s -> s.allows(type) && s.email().equals(address))
        .map(s -> new Eligibility(true, unsubscribeToken(s)))
        .orElse(new Eligibility(false, null));
  }

  /** 링크만으로 끌 수 있어요. 켜기·주소 변경 권한은 주지 않아요. */
  @Transactional
  public void unsubscribe(String token) {
    if (token == null || !token.matches("[a-f0-9-]{36}\\.[a-f0-9]{64}")) throw invalid();
    UUID id;
    try {
      id = UUID.fromString(token.substring(0, 36));
    } catch (IllegalArgumentException e) {
      throw invalid();
    }
    if (emails.find(id).isEmpty()) throw invalid();
    emails.lock(id);
    Saved saved = emails.find(id).orElseThrow(EmailNotificationService::invalid);
    if (!equal(token, unsubscribeToken(saved))) throw invalid();
    emails.settings(
        id, false, saved.newNotice(), saved.deadline(), saved.reportAnswer(), clock.instant());
  }

  private String unsubscribeToken(Saved saved) {
    if (secret.isBlank()) throw new CustomException(ErrorCode.EMAIL_DELIVERY_UNAVAILABLE);
    try {
      Mac mac = Mac.getInstance("HmacSHA256");
      mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
      String payload = "email-unsubscribe-v1:" + saved.userId() + ":" + saved.nonce();
      return saved.userId()
          + "."
          + HexFormat.of().formatHex(mac.doFinal(payload.getBytes(StandardCharsets.UTF_8)));
    } catch (java.security.GeneralSecurityException e) {
      throw new IllegalStateException("Email signature unavailable");
    }
  }

  private Status status(Saved s) {
    return new Status(
        s.email(),
        s.verifiedAt() != null,
        s.enabled(),
        s.newNotice(),
        s.deadline(),
        s.reportAnswer());
  }

  private static String randomToken() {
    byte[] bytes = new byte[32];
    RANDOM.nextBytes(bytes);
    return HexFormat.of().formatHex(bytes);
  }

  static String hash(String token) {
    try {
      return HexFormat.of()
          .formatHex(
              MessageDigest.getInstance("SHA-256").digest(token.getBytes(StandardCharsets.UTF_8)));
    } catch (java.security.NoSuchAlgorithmException e) {
      throw new IllegalStateException("SHA-256 unavailable");
    }
  }

  private static boolean equal(String a, String b) {
    return MessageDigest.isEqual(
        a.getBytes(StandardCharsets.UTF_8), b.getBytes(StandardCharsets.UTF_8));
  }

  private static CustomException invalid() {
    return new CustomException(ErrorCode.EMAIL_VERIFICATION_INVALID);
  }
}
