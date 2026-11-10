package kr.mujuthaek.notification.delivery.email;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * 메일 설정 (notification.mail.*). AWS 키는 여기 넣지 않아요. SES 클라이언트가 AWS_PROFILE(~/.aws/credentials)이나 서버
 * 역할에서 읽어요.
 *
 * @param provider {@code log}: 보내지 않고 로그만 (기본), {@code ses}: AWS SES로 보내기
 * @param from 보내는 주소. SES에서 인증한 주소여야 해요
 * @param webBaseUrl 메일 속 링크 앞부분 (PWA 주소)
 */
@ConfigurationProperties("notification.mail")
public record MailProperties(
    @DefaultValue("log") String provider,
    @DefaultValue("noreply@localhost") String from,
    @DefaultValue("http://localhost:5173") String webBaseUrl,
    @DefaultValue Ses ses) {

  /**
   * @param maxPerSecond 초당 최대 발송 수. 샌드박스는 1통이에요
   */
  public record Ses(
      @DefaultValue("ap-northeast-2") String region, @DefaultValue("1") int maxPerSecond) {}
}
