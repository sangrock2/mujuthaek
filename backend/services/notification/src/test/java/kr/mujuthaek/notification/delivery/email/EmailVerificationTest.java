package kr.mujuthaek.notification.delivery.email;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.*;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class EmailVerificationTest {
  final EmailSender sender = mock(EmailSender.class);
  final String secret = "private-internal-token";
  Instant now = Instant.parse("2026-11-16T03:00:00Z");
  final Clock clock =
      new Clock() {
        @Override
        public java.time.ZoneId getZone() {
          return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(java.time.ZoneId zone) {
          return this;
        }

        @Override
        public Instant instant() {
          return now;
        }
      };

  EmailVerificationController controller(String provider) {
    return controller(provider, new VerificationMailLimiter(clock, 3, 10, 120));
  }

  EmailVerificationController controller(String provider, VerificationMailLimiter limiter) {
    return new EmailVerificationController(sender, properties(provider), limiter, secret);
  }

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
    var controller = controller("ses");
    assertThat(controller.send("", request()).getStatusCode().value()).isEqualTo(403);
    verifyNoInteractions(sender);
  }

  @Test
  void logModeNeverLogsOrPretendsToSendVerificationTokens() {
    var controller = controller("log");
    assertThat(controller.send("Bearer " + secret, request()).getStatusCode().value())
        .isEqualTo(503);
    verifyNoInteractions(sender);
  }

  /** 보안 감사 M-3: 계정을 여러 개 만들어도 한 주소로 인증 메일을 계속 보내지 못해요. */
  @Test
  void oneAddressReceivesAtMostThreeVerificationMailsAnHour() throws Exception {
    var controller = controller("ses");
    for (int i = 0; i < 3; i++) {
      assertThat(controller.send("Bearer " + secret, request()).getStatusCode().value())
          .isEqualTo(204);
    }
    var upperCase = new EmailVerificationController.Request("A@Example.com", "a".repeat(64));
    assertThat(controller.send("Bearer " + secret, upperCase).getStatusCode().value())
        .isEqualTo(429);
    verify(sender, times(3)).send(any());

    now = now.plus(Duration.ofHours(1)).plusSeconds(1);
    assertThat(controller.send("Bearer " + secret, request()).getStatusCode().value())
        .isEqualTo(204);
  }

  @Test
  void theWholeServerSendsAtMostTheGlobalBudgetAnHour() throws Exception {
    var controller = controller("ses", new VerificationMailLimiter(clock, 3, 10, 2));
    for (String to : new String[] {"a@example.com", "b@example.com"}) {
      var each = new EmailVerificationController.Request(to, "a".repeat(64));
      assertThat(controller.send("Bearer " + secret, each).getStatusCode().value()).isEqualTo(204);
    }
    var third = new EmailVerificationController.Request("c@example.com", "a".repeat(64));
    assertThat(controller.send("Bearer " + secret, third).getStatusCode().value()).isEqualTo(429);
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        "Name<a@example.com>",
        "\"x\"<a@example.com>",
        "x,y<a@example.com>",
        "a@[10.0.0.1]"
      })
  void displayNameAddressesAreRefused(String address) {
    var controller = controller("ses");
    var body = new EmailVerificationController.Request(address, "a".repeat(64));
    assertThat(controller.send("Bearer " + secret, body).getStatusCode().value()).isEqualTo(400);
    verifyNoInteractions(sender);
  }

  @Test
  void authorizedRequestIncludesOneTimeFragmentLink() throws Exception {
    var controller = controller("ses");
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
