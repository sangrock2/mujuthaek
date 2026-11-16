package kr.mujuthaek.notification.delivery.email;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.notification.delivery.Channel;
import kr.mujuthaek.notification.delivery.DeliveryException;
import kr.mujuthaek.notification.delivery.DigestCadence;
import kr.mujuthaek.notification.delivery.NotificationChannel;
import kr.mujuthaek.notification.delivery.OutgoingNotification;
import kr.mujuthaek.notification.notification.NotificationRequest;
import org.springframework.stereotype.Component;

/** 이메일 채널. 받을 곳은 요청의 recipients[].email이고, 새 공고·새 정책은 하루 두 번 묶어 1통으로 보내요. */
@Component
class EmailChannel implements NotificationChannel {

  private final EmailSender sender;
  private final MailProperties properties;
  private final EmailConsentClient consent;

  EmailChannel(EmailSender sender, MailProperties properties, EmailConsentClient consent) {
    this.sender = sender;
    this.properties = properties;
    this.consent = consent;
  }

  @Override
  public Channel channel() {
    return Channel.EMAIL;
  }

  @Override
  public Optional<String> address(NotificationRequest.Recipient recipient) {
    return Optional.ofNullable(recipient.email()).filter(email -> !email.isBlank());
  }

  @Override
  public Optional<DigestCadence> digestCadence() {
    return Optional.of(DigestCadence.TWICE_A_DAY);
  }

  @Override
  public String send(UUID userId, String address, List<OutgoingNotification> notifications)
      throws DeliveryException {
    String unsubscribe = "";
    if ("ses".equals(properties.provider())) {
      var allowed = new java.util.ArrayList<OutgoingNotification>();
      for (OutgoingNotification n : notifications) {
        var result = consent.check(userId, address, n.type().name());
        if (result.allowed()) {
          allowed.add(n);
          unsubscribe = result.unsubscribeToken();
        }
      }
      if (allowed.isEmpty()) throw new DeliveryException("EMAIL_CONSENT_WITHDRAWN", true);
      notifications = allowed;
    }
    String body = text(notifications);
    if (!unsubscribe.isBlank())
      body +=
          "\n이메일 수신 해제: "
              + properties.webBaseUrl()
              + "/email/unsubscribe#token="
              + unsubscribe
              + "\n";
    return sender.send(
        new EmailMessage(
            address, subject(notifications), body, oneClickUnsubscribeUrl(unsubscribe)));
  }

  /**
   * 메일 앱의 「수신 거부」 버튼이 부르는 주소(RFC 8058 한 번 눌러 해제). 메일 앱은 이 주소에 {@code List-Unsubscribe=One-Click}를
   * POST해요. 웹 주소의 {@code /api/**}는 api 서버로 넘어가서 api의 {@code POST
   * /api/email-notifications/unsubscribe/one-click}이 받아요. RFC가 https만 허용해서 로컬(http)은 붙이지
   * 않아요(2026-11-16 보안 감사 4장).
   */
  String oneClickUnsubscribeUrl(String token) {
    String base = properties.webBaseUrl();
    if (token == null || token.isBlank() || base == null || !base.startsWith("https://")) {
      return null;
    }
    return base.replaceAll("/+$", "")
        + "/api/email-notifications/unsubscribe/one-click?token="
        + URLEncoder.encode(token, StandardCharsets.UTF_8);
  }

  private static String subject(List<OutgoingNotification> notifications) {
    String subject =
        notifications.size() == 1
            ? "[무주택자들] " + notifications.getFirst().title()
            : "[무주택자들] 관심 조건에 맞는 새 소식 " + notifications.size() + "건";
    return oneLine(subject);
  }

  /** 메일 제목은 한 줄이어야 해요. 줄바꿈이 들어오면 메일 머리글이 깨지거나 SES가 거절해요 */
  static String oneLine(String value) {
    return value.replaceAll("[\\r\\n]+", " ").strip();
  }

  private String text(List<OutgoingNotification> notifications) {
    StringBuilder sb = new StringBuilder();
    for (OutgoingNotification n : notifications) {
      sb.append("■ ").append(n.title()).append('\n');
      sb.append(n.body()).append('\n');
      sb.append(properties.webBaseUrl()).append(n.linkPath()).append("\n\n");
    }
    sb.append("---\n");
    sb.append("알림 설정은 여기서 바꿀 수 있어요: ")
        .append(properties.webBaseUrl())
        .append("/settings/notifications\n");
    return sb.toString();
  }
}
