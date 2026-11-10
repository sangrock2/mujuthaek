package kr.mujuthaek.notification.delivery.push;

import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * 웹 푸시 설정 (notification.push.*). VAPID 개인키는 커밋하지 않고 .env·배포 비밀값(PUSH_VAPID_PRIVATE_KEY)에만 둬요.
 *
 * @param provider {@code log}: 보내지 않고 로그만 (기본), {@code webpush}: 푸시 서비스로 보내기
 * @param vapidPublicKey VAPID 공개키 (base64url, 65바이트). api가 PWA에 주는 값과 같아야 해요
 * @param vapidPrivateKey VAPID 개인키 (base64url, 32바이트). {@code npx web-push generate-vapid-keys}로 만든
 *     값
 * @param vapidSubject 푸시 서비스가 문제 있을 때 연락할 곳 ({@code mailto:} 또는 {@code https:} 주소)
 * @param allowedHosts 보낼 수 있는 푸시 서비스 도메인 (그 도메인 또는 하위 도메인). api도 같은 목록으로 구독을 받아요. 다른 주소는 보내지 않아요
 * @param timeout 기기 한 대에 보내는 요청의 최대 시간
 */
@ConfigurationProperties("notification.push")
public record PushProperties(
    @DefaultValue("log") String provider,
    @DefaultValue("") String vapidPublicKey,
    @DefaultValue("") String vapidPrivateKey,
    @DefaultValue("mailto:noreply@localhost") String vapidSubject,
    @DefaultValue({
          "fcm.googleapis.com",
          "push.services.mozilla.com",
          "push.apple.com",
          "notify.windows.com"
        })
        List<String> allowedHosts,
    @DefaultValue("5s") Duration timeout) {

  /** 그 도메인이거나 하위 도메인이면 true (예: web.push.apple.com → push.apple.com) */
  boolean allows(String host) {
    return host != null
        && allowedHosts.stream().anyMatch(h -> host.equals(h) || host.endsWith("." + h));
  }
}
