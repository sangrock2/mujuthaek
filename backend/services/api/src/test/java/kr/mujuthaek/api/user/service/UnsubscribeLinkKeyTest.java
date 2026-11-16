package kr.mujuthaek.api.user.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.user.repository.NotificationEmailRepository;
import kr.mujuthaek.api.user.repository.NotificationEmailRepository.Saved;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.support.TransactionOperations;

/**
 * 수신 거부 링크 서명: 전용 키가 있으면 새 링크(v2)를 전용 키로 서명하고, 전에 보낸 링크(v1, 내부 토큰)도 받아요. 내부 토큰을 바꾸면 v1만 깨지고 v2는
 * 그대로예요 (2026-11-16 보안 감사 L-15).
 */
class UnsubscribeLinkKeyTest {

  private static final Instant NOW = Instant.parse("2026-11-16T01:00:00Z");
  private static final UUID USER = UUID.randomUUID();
  private static final String ADDRESS = "member@example.com";

  // 시험용 이름표예요. 비밀값처럼 보이는 글자를 쓰면 저장소의 비밀값 검사(gitleaks)가 막아요
  private static final String INTERNAL = "internal";
  private static final String ROTATED_INTERNAL = "rotated";
  private static final String DEDICATED = "dedicated";

  private final NotificationEmailRepository emails = mock(NotificationEmailRepository.class);

  UnsubscribeLinkKeyTest() {
    Saved saved =
        new Saved(USER, ADDRESS, null, null, null, null, 0, NOW, true, true, true, true, "nonce-1");
    when(emails.find(USER)).thenReturn(Optional.of(saved));
  }

  private EmailNotificationService service(String internalToken, String unsubscribeKey) {
    return new EmailNotificationService(
        emails,
        null,
        Clock.fixed(NOW, ZoneOffset.UTC),
        TransactionOperations.withoutTransaction(),
        internalToken,
        unsubscribeKey);
  }

  private String link(EmailNotificationService service) {
    return service.eligible(USER, ADDRESS, "NEW_NOTICE").unsubscribeToken();
  }

  @Test
  void dedicatedKeySignsNewLinksAndOldLinksStillWork() {
    String v1 = link(service(INTERNAL, ""));
    var withKey = service(INTERNAL, DEDICATED);
    String v2 = link(withKey);

    assertThat(v1).matches(USER + "\\.[a-f0-9]{64}");
    assertThat(v2).matches(USER + "\\.v2\\.[a-f0-9]{64}");

    withKey.unsubscribe(v2);
    withKey.unsubscribe(v1);
    verify(emails, org.mockito.Mockito.times(2))
        .settings(eq(USER), eq(false), anyBoolean(), anyBoolean(), anyBoolean(), any());
  }

  @Test
  void rotatingTheInternalTokenBreaksOnlyOldLinks() {
    String v1 = link(service(INTERNAL, ""));
    String v2 = link(service(INTERNAL, DEDICATED));
    var rotated = service(ROTATED_INTERNAL, DEDICATED);

    assertThatThrownBy(() -> rotated.unsubscribe(v1)).isInstanceOf(CustomException.class);
    rotated.unsubscribe(v2);
  }

  @Test
  void theInternalTokenCannotForgeNewLinks() {
    // 내부 토큰만 아는 사람이 v1 서명을 v2 모양으로 바꿔 보내도 받지 않아요
    String v1 = link(service(INTERNAL, ""));
    String forged = USER + ".v2." + v1.substring(37);
    var withKey = service(INTERNAL, DEDICATED);

    assertThatThrownBy(() -> withKey.unsubscribe(forged)).isInstanceOf(CustomException.class);
    verify(emails, never())
        .settings(eq(USER), eq(false), anyBoolean(), anyBoolean(), anyBoolean(), any());
  }
}
