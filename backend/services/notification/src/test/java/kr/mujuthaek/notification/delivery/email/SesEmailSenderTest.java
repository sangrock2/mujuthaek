package kr.mujuthaek.notification.delivery.email;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class SesEmailSenderTest {

  private final MailProperties properties =
      new MailProperties(
          "ses",
          "noreply@example.com",
          "https://example.com",
          new MailProperties.Ses("ap-northeast-2", 1));

  @Test
  void bounceFeedbackAndRepliesGoToTheConfiguredContactAddress() {
    try (var sender = new SesEmailSender(properties, "contact@example.com")) {
      var request = sender.request(new EmailMessage("owner@example.com", "테스트", "본문"));
      assertThat(request.fromEmailAddress()).isEqualTo("noreply@example.com");
      assertThat(request.feedbackForwardingEmailAddress()).isEqualTo("contact@example.com");
      assertThat(request.replyToAddresses()).containsExactly("contact@example.com");
      assertThat(request.content().simple().subject().charset()).isEqualTo("UTF-8");
    }
  }

  @Test
  void oneClickUnsubscribeHeadersAreAddedOnlyWhenThereIsALink() {
    // RFC 8058 한 번 눌러 해제 (2026-11-16 보안 감사 4장)
    String url = "https://example.com/api/email-notifications/unsubscribe/one-click?token=t";
    try (var sender = new SesEmailSender(properties, "")) {
      var headers =
          sender
              .request(new EmailMessage("owner@example.com", "알림", "본문", url))
              .content()
              .simple()
              .headers();
      assertThat(headers)
          .extracting(h -> h.name() + ": " + h.value())
          .containsExactly(
              "List-Unsubscribe: <" + url + ">",
              "List-Unsubscribe-Post: List-Unsubscribe=One-Click");

      assertThat(
              sender
                  .request(new EmailMessage("owner@example.com", "인증", "본문"))
                  .content()
                  .simple()
                  .headers())
          .isEmpty();
    }
  }

  @Test
  void existingSettingsWithoutFeedbackAddressRemainUsable() {
    try (var sender = new SesEmailSender(properties, "")) {
      var request = sender.request(new EmailMessage("owner@example.com", "test", "body"));
      assertThat(request.feedbackForwardingEmailAddress()).isNull();
      assertThat(request.replyToAddresses()).isEmpty();
    }
  }

  @Test
  void configuredFeedbackSetIsAttachedToEverySend() {
    var configured =
        new MailProperties(
            "ses",
            "noreply@example.com",
            "https://example.com",
            new MailProperties.Ses("ap-northeast-2", 1, "mujuthaek-feedback"));
    try (var sender = new SesEmailSender(configured, "")) {
      assertThat(
              sender
                  .request(new EmailMessage("owner@example.com", "test", "body"))
                  .configurationSetName())
          .isEqualTo("mujuthaek-feedback");
    }
  }
}
