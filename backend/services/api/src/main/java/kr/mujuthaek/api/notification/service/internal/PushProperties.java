package kr.mujuthaek.api.notification.service.internal;

import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.context.annotation.Configuration;

/**
 * 웹 푸시 설정 (app.push). 개인키는 알림 서버만 가져서 여기에는 공개키만 있어요.
 *
 * @param vapidPublicKey PWA가 구독할 때 쓰는 VAPID 공개키 (PUSH_VAPID_PUBLIC_KEY). 비어 있으면 구독을 받지 않아요
 * @param allowedHosts 받을 수 있는 구독 주소(endpoint)의 푸시 서비스 도메인. 그 도메인이거나 그 하위 도메인이어야 해요. 알림 서버가 이 주소로
 *     요청을 보내서, 아무 주소나 받으면 우리 서버가 남의 서버를 부르게 돼요
 * @param maxDevices 회원 한 명이 둘 수 있는 기기 수. 넘으면 가장 오래 안 쓴 기기를 지워요
 */
@ConfigurationProperties("app.push")
public record PushProperties(
    @DefaultValue("") String vapidPublicKey,
    @DefaultValue({
          "fcm.googleapis.com",
          "push.services.mozilla.com",
          "push.apple.com",
          "notify.windows.com"
        })
        List<String> allowedHosts,
    @DefaultValue("5") int maxDevices) {

  /** 그 도메인이거나 하위 도메인이면 true (예: web.push.apple.com → push.apple.com) */
  boolean allows(String host) {
    return host != null
        && allowedHosts.stream().anyMatch(h -> host.equals(h) || host.endsWith("." + h));
  }

  @Configuration
  @EnableConfigurationProperties(PushProperties.class)
  static class Config {}
}
