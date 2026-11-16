package kr.mujuthaek.notification.notification;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/**
 * 보안 감사 M-8: linkPath는 「/」로 시작하는지만 봐서 「//다른곳」이 통과했고, 서비스 워커가 그 주소를 열어 우리 키로 서명된 피싱 알림이 될 수 있었어요. 앱
 * 안 화면 경로만 받아요.
 */
class NotificationLinkPathTest {

  private static NotificationRequest request(String linkPath) {
    return new NotificationRequest(
        NotificationType.NEW_NOTICE,
        "dedup-1",
        new NotificationRequest.Target(TargetType.NOTICE, UUID.randomUUID()),
        "새 공고",
        "관심 지역에 새 공고가 올라왔어요",
        linkPath,
        List.of(
            NotificationRequest.Recipient.emailOnly(UUID.randomUUID(), "me@example.com", false)));
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        "/notifications",
        "/notices/018f6b5e-1c2d-7abc-8def-0123456789ab",
        "/business/support/018f6b5e-1c2d-7abc-8def-0123456789ab",
        "/me?tab=reports"
      })
  void appScreensAreAccepted(String linkPath) {
    assertThatCode(() -> request(linkPath).validate()).doesNotThrowAnyException();
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        "//evil.example/login",
        "/\\evil.example",
        "/\t/evil.example",
        "https://evil.example",
        "javascript:alert(1)",
        "/notices/a b",
        "/@evil.example",
        "notices/1"
      })
  void offSiteOrMalformedLinksAreRejected(String linkPath) {
    assertThatThrownBy(() -> request(linkPath).validate())
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessage("linkPath가 이상해요");
  }

  @Test
  void overlongLinksAreRejected() {
    assertThatThrownBy(() -> request("/notices/" + "a".repeat(400)).validate())
        .isInstanceOf(IllegalArgumentException.class);
  }
}
