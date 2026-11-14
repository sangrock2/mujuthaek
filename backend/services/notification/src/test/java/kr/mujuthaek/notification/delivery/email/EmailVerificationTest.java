package kr.mujuthaek.notification.delivery.email;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;

class EmailVerificationTest {
  final EmailSender sender = mock(EmailSender.class);
  final String secret = "private-internal-token";

  MailProperties properties(String provider) {
    return new MailProperties(
        provider,
        "noreply@example.com",
        "https://mujuthaek.store",
        new MailProperties.Ses("ap-northeast-2", 1));
  }

  EmailVerificationController.Request request() {
    return new EmailVerificationController.Request("a@example.com", "a".repeat(64));
  }

  @Test
  void internalCredentialIsRequiredBeforeAnySend() {
    var controller = new EmailVerificationController(sender, properties("ses"), secret);
    assertThat(controller.send("", request()).getStatusCode().value()).isEqualTo(403);
    verifyNoInteractions(sender);
  }

  @Test
  void logModeNeverLogsOrPretendsToSendVerificationTokens() {
    var controller = new EmailVerificationController(sender, properties("log"), secret);
    assertThat(controller.send("Bearer " + secret, request()).getStatusCode().value())
        .isEqualTo(503);
    verifyNoInteractions(sender);
  }

  @Test
  void authorizedRequestIncludesOneTimeFragmentLink() throws Exception {
    var controller = new EmailVerificationController(sender, properties("ses"), secret);
    assertThat(controller.send("Bearer " + secret, request()).getStatusCode().value())
        .isEqualTo(204);
    verify(sender)
        .send(
            argThat(
                message ->
                    message
                        .text()
                        .contains("https://mujuthaek.store/email/verify#token=" + "a".repeat(64))));
  }
}
