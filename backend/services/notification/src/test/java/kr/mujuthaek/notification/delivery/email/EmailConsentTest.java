package kr.mujuthaek.notification.delivery.email;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import java.util.List;
import java.util.UUID;
import kr.mujuthaek.notification.delivery.DeliveryException;
import kr.mujuthaek.notification.delivery.OutgoingNotification;
import kr.mujuthaek.notification.notification.NotificationType;
import org.junit.jupiter.api.Test;

class EmailConsentTest {
  final EmailSender sender = mock(EmailSender.class);
  final EmailConsentClient consent = mock(EmailConsentClient.class);
  final MailProperties properties =
      new MailProperties(
          "ses",
          "noreply@example.com",
          "https://example.com",
          new MailProperties.Ses("ap-northeast-2", 1));
  final EmailChannel channel = new EmailChannel(sender, properties, consent);
  final UUID user = UUID.randomUUID();
  final OutgoingNotification notice =
      new OutgoingNotification(NotificationType.NEW_NOTICE, "새 공고", "새 소식", "/notices/one");

  @Test
  void withdrawnConsentNeverReachesSes() throws Exception {
    when(consent.check(any(), anyString(), anyString()))
        .thenReturn(new EmailConsentClient.Consent(false, null));
    assertThatThrownBy(() -> channel.send(user, "a@example.com", List.of(notice)))
        .isInstanceOf(DeliveryException.class);
    verifyNoInteractions(sender);
  }

  @Test
  void consentLookupFailureDoesNotSend() throws Exception {
    when(consent.check(any(), anyString(), anyString()))
        .thenThrow(new DeliveryException("EMAIL_CONSENT_UNAVAILABLE", false));
    assertThatThrownBy(() -> channel.send(user, "a@example.com", List.of(notice)))
        .isInstanceOf(DeliveryException.class);
    verifyNoInteractions(sender);
  }

  @Test
  void verifiedConsentingRecipientReceivesUnsubscribeLink() throws Exception {
    when(consent.check(any(), anyString(), anyString()))
        .thenReturn(new EmailConsentClient.Consent(true, "signed-token"));
    channel.send(user, "a@example.com", List.of(notice));
    verify(sender)
        .send(argThat(message -> message.text().contains("/email/unsubscribe#token=signed-token")));
  }
}
