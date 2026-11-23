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
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionOperations;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.client.RestClientException;

/** 연락용 이메일과 별도 동의. 인증·수신 동의가 모두 있어야 알림 주소를 반환해요. */
@Service
public class EmailNotificationService {
  private static final SecureRandom RANDOM = new SecureRandom();
  private final NotificationEmailRepository emails;
  private final EmailVerificationSender mail;
  private final Clock clock;
  private final TransactionOperations transactions;

  /** 알림 서버와 주고받는 내부 토큰. 전용 키가 없을 때와, 전에 보낸 수신 거부 링크(v1)를 확인할 때만 써요 */
  private final String secret;

  /** 수신 거부 링크 전용 서명 키(EMAIL_UNSUBSCRIBE_KEY). 있으면 새 링크(v2)를 이 키로 서명해요 */
  private final String unsubscribeKey;

  @Autowired
  public EmailNotificationService(
      NotificationEmailRepository emails,
      EmailVerificationSender mail,
      Clock clock,
      PlatformTransactionManager transactionManager,
      @Value("${mujuthaek.notification.server.token:}") String secret,
      @Value("${mujuthaek.email-notifications.unsubscribe-key:}") String unsubscribeKey) {
    this(emails, mail, clock, new TransactionTemplate(transactionManager), secret, unsubscribeKey);
  }

  EmailNotificationService(
      NotificationEmailRepository emails,
      EmailVerificationSender mail,
      Clock clock,
      TransactionOperations transactions,
      String secret,
      String unsubscribeKey) {
    this.emails = emails;
    this.mail = mail;
    this.clock = clock;
    this.transactions = transactions;
    this.secret = secret == null ? "" : secret;
    this.unsubscribeKey = unsubscribeKey == null ? "" : unsubscribeKey.strip();
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

  /**
   * 인증 메일 요청. 시도(횟수·시각·토큰 해시)를 짧은 트랜잭션으로 먼저 커밋하고, 메일은 트랜잭션·행 잠금 밖에서 보내요.
   *
   * <p>예전에는 잠금을 쥔 트랜잭션 안에서 알림 서버를 불렀어요. 호출이 시간 초과(5초)로 실패하면 트랜잭션이 되돌려지며 횟수 기록도 사라졌지만 알림 서버는 메일을
   * 보내서, 계정 몇 개로 남의 주소에 인증 메일을 끝없이 보낼 수 있었고 그동안 DB 연결과 잠금도 붙잡혔어요(2026-11-16 보안 감사 M-3). 이제 보내기에
   * 실패해도 시도는 남고(1분·하루 5회 제한이 그대로 적용), 늦게 도착한 메일의 링크도 쓸 수 있어요.
   */
  public Status request(UUID id, String input) {
    String address = ContactEmailService.normalize(input);
    String token = randomToken();
    transactions.executeWithoutResult(
        status -> {
          emails.lock(id);
          var now = clock.instant();
          var day = now.atZone(ZoneId.of("Asia/Seoul")).toLocalDate();
          Saved previous = emails.find(id).orElse(null);
          if (previous != null
              && previous.email() != null
              && (previous.verifiedAt() != null || !previous.email().equals(address))) {
            throw new CustomException(ErrorCode.EMAIL_ADDRESS_LOCKED);
          }
          int count =
              previous != null && day.equals(previous.requestDay()) ? previous.requestCount() : 0;
          if (count >= 5
              || previous != null && previous.requestedAt().plusSeconds(60).isAfter(now)) {
            throw new CustomException(ErrorCode.RATE_LIMITED);
          }
          emails.request(id, address, hash(token), randomToken(), now, day, count + 1);
        });
    try {
      mail.sendEmailVerification(address, token);
    } catch (RestClientException e) {
      throw new CustomException(ErrorCode.EMAIL_DELIVERY_UNAVAILABLE);
    }
    return get(id);
  }

  @Transactional
  public void verifyLink(String token) {
    consumeLink(token, null);
  }

  @Transactional
  public Status verify(UUID id, String token) {
    consumeLink(token, id);
    return get(id);
  }

  private void consumeLink(String token, UUID owner) {
    if (token == null
        || !token.matches("[a-f0-9]{64}")
        || !emails.consumeVerification(hash(token), owner, clock.instant())) {
      throw invalid();
    }
  }

  @Transactional
  public Status save(UUID id, Settings s) {
    emails.lock(id);
    if (!s.enabled()) {
      emails.withdraw(id, clock.instant());
      return get(id);
    }
    Saved saved = emails.find(id).orElseThrow(EmailNotificationService::invalid);
    if (saved.verifiedAt() == null || (!saved.enabled() && !s.consent())) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "인증된 이메일과 수신 동의가 필요해요");
    }
    if (!s.newNotice() && !s.deadline() && !s.reportAnswer()) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "받을 알림을 하나 이상 골라 주세요");
    }
    emails.settings(id, true, s.newNotice(), s.deadline(), s.reportAnswer(), clock.instant());
    return get(id);
  }

  @Transactional
  public void withdraw(UUID id) {
    emails.lock(id);
    emails.withdraw(id, clock.instant());
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

  /**
   * 링크만으로 끌 수 있어요. 켜기·주소 변경 권한은 주지 않아요. 새 링크(v2, 전용 키)와 전에 보낸 링크(v1, 내부 토큰)를 모두 받아요 — 내부 토큰을 바꾸면 v1
   * 링크만 깨지고 v2 링크는 그대로예요.
   */
  @Transactional
  public void unsubscribe(String token) {
    boolean v2 = token != null && token.matches("[a-f0-9-]{36}\\.v2\\.[a-f0-9]{64}");
    boolean v1 = token != null && token.matches("[a-f0-9-]{36}\\.[a-f0-9]{64}");
    if (!v1 && !v2) throw invalid();
    UUID id;
    try {
      id = UUID.fromString(token.substring(0, 36));
    } catch (IllegalArgumentException e) {
      throw invalid();
    }
    if (emails.find(id).isEmpty()) throw invalid();
    emails.lock(id);
    Saved saved = emails.find(id).orElseThrow(EmailNotificationService::invalid);
    String expected = v2 ? signedV2(saved) : signedV1(saved);
    if (expected == null || !equal(token, expected)) throw invalid();
    emails.withdraw(id, clock.instant());
  }

  /**
   * 메일에 넣을 수신 거부 링크 토큰. 전용 키가 있으면 v2(전용 키), 없으면 예전처럼 v1(알림 서버 내부 토큰)이에요. 예전에는 서비스 간 토큰 하나를 링크 서명
   * 키로도 써서, 한쪽에서만 새어도 모든 회원의 수신 거부 링크를 만들 수 있었고 토큰을 바꾸면 보낸 링크가 모두 깨졌어요(2026-11-16 보안 감사 L-15).
   */
  private String unsubscribeToken(Saved saved) {
    String token = unsubscribeKey.isBlank() ? signedV1(saved) : signedV2(saved);
    if (token == null) throw new CustomException(ErrorCode.EMAIL_DELIVERY_UNAVAILABLE);
    return token;
  }

  /** 전용 키로 서명한 링크. 키가 없으면 null */
  private String signedV2(Saved saved) {
    if (unsubscribeKey.isBlank()) return null;
    return saved.userId()
        + ".v2."
        + hmac(unsubscribeKey, "email-unsubscribe-v2:" + saved.userId() + ":" + saved.nonce());
  }

  /** 예전 링크: 알림 서버 내부 토큰으로 서명. 토큰이 없으면 null */
  private String signedV1(Saved saved) {
    if (secret.isBlank()) return null;
    return saved.userId()
        + "."
        + hmac(secret, "email-unsubscribe-v1:" + saved.userId() + ":" + saved.nonce());
  }

  private static String hmac(String key, String payload) {
    try {
      Mac mac = Mac.getInstance("HmacSHA256");
      mac.init(new SecretKeySpec(key.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
      return HexFormat.of().formatHex(mac.doFinal(payload.getBytes(StandardCharsets.UTF_8)));
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
