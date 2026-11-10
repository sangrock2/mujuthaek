package kr.mujuthaek.api.notification;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.Base64;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.notification.repository.PushSubscriptionRepository;
import kr.mujuthaek.api.notification.service.internal.PushProperties;
import kr.mujuthaek.api.notification.service.internal.PushSubscriptionService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/** 구독 주소·키 검사와 설정이 없을 때 (DB 없이). */
class PushSubscriptionServiceTest {

  static final List<String> HOSTS =
      List.of(
          "fcm.googleapis.com",
          "push.services.mozilla.com",
          "push.apple.com",
          "notify.windows.com");

  final PushSubscriptionRepository repository = mock(PushSubscriptionRepository.class);
  final Clock clock = Clock.fixed(Instant.parse("2026-10-26T00:00:00Z"), ZoneId.of("Asia/Seoul"));
  final UUID userId = UUID.randomUUID();

  PushSubscriptionService service(String publicKey) {
    return new PushSubscriptionService(repository, new PushProperties(publicKey, HOSTS, 5), clock);
  }

  @Test
  void withoutAPublicKeyNothingIsAccepted() {
    PushSubscriptionService service = service("");

    assertThatThrownBy(service::publicKey)
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.PUSH_NOT_CONFIGURED));
    assertThatThrownBy(
            () ->
                service.subscribe(
                    userId, "https://fcm.googleapis.com/fcm/send/a", p256dh(), auth(), null))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.PUSH_NOT_CONFIGURED));
    verifyNoInteractions(repository);
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        "https://fcm.googleapis.com/fcm/send/a",
        "https://updates.push.services.mozilla.com/wpush/v2/a",
        "https://web.push.apple.com/QGl4",
        "https://wns2-par02p.notify.windows.com/w/?token=a"
      })
  void pushServiceAddressesAreAccepted(String endpoint) {
    service("k").subscribe(userId, endpoint, p256dh(), auth(), null);

    verify(repository).upsert(eq(userId), eq(endpoint), any(), any(), any(), any());
    verify(repository).keepLatest(userId, 5);
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        "https://evilpush.apple.com/a", // 하위 도메인이 아니라 이름만 비슷함
        "https://push.apple.com.evil.com/a",
        "https://fcm.googleapis.com:8443/a",
        "https://user@fcm.googleapis.com/a",
        "http://fcm.googleapis.com/a",
        "https://localhost/a",
        "not a url",
        "https:opaque", // 도메인이 없음
        " "
      })
  void otherAddressesAreRejectedWithoutTheValue(String endpoint) {
    assertThatThrownBy(() -> service("k").subscribe(userId, endpoint, p256dh(), auth(), null))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> {
              assertThat(e.errorCode()).isEqualTo(ErrorCode.VALIDATION_FAILED);
              assertThat(e.getMessage()).startsWith("endpoint: ");
              if (!endpoint.isBlank()) {
                assertThat(e.getMessage()).doesNotContain(endpoint);
              }
            });
    verifyNoInteractions(repository);
  }

  @Test
  void missingEndpointOrKeysAreRejected() {
    PushSubscriptionService service = service("k");
    String endpoint = "https://fcm.googleapis.com/a";

    assertThatThrownBy(() -> service.subscribe(userId, null, p256dh(), auth(), null))
        .hasMessage("endpoint: 꼭 있어야 해요");
    assertThatThrownBy(() -> service.subscribe(userId, endpoint, null, auth(), null))
        .hasMessage("keys.p256dh: 꼭 있어야 해요");
    assertThatThrownBy(() -> service.subscribe(userId, endpoint, p256dh(), " ", null))
        .hasMessage("keys.auth: 꼭 있어야 해요");
    verifyNoInteractions(repository);
  }

  @Test
  void tooLongEndpointIsRejected() {
    String endpoint = "https://fcm.googleapis.com/" + "a".repeat(2048);

    assertThatThrownBy(() -> service("k").subscribe(userId, endpoint, p256dh(), auth(), null))
        .hasMessage("endpoint: 2048자를 넘어요");
  }

  @Test
  void paddedBase64urlKeysAreFineAndLongLabelsAreCut() {
    String padded = Base64.getUrlEncoder().encodeToString(new byte[16]); // == 로 끝남

    service("k")
        .subscribe(userId, "https://fcm.googleapis.com/a", p256dh(), padded, "가".repeat(300));

    verify(repository)
        .upsert(any(), any(), any(), eq(padded), eq("가".repeat(200)), eq(clock.instant()));
  }

  @Test
  void blankLabelIsStoredAsNull() {
    service("k").subscribe(userId, "https://fcm.googleapis.com/a", p256dh(), auth(), "  ");

    verify(repository).upsert(any(), any(), any(), any(), eq(null), any());
    verify(repository).keepLatest(eq(userId), anyInt());
  }

  private static String p256dh() {
    byte[] point = new byte[65];
    point[0] = 0x04;
    return Base64.getUrlEncoder().withoutPadding().encodeToString(point);
  }

  private static String auth() {
    return Base64.getUrlEncoder().withoutPadding().encodeToString(new byte[16]);
  }
}
