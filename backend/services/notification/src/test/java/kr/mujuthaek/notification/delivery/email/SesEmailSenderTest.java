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
  void existingSettingsWithoutFeedbackAddressRemainUsable() {
    try (var sender = new SesEmailSender(properties, "")) {
      var request = sender.request(new EmailMessage("owner@example.com", "test", "body"));
      assertThat(request.feedbackForwardingEmailAddress()).isNull();
      assertThat(request.replyToAddresses()).isEmpty();
    }
  }
}
