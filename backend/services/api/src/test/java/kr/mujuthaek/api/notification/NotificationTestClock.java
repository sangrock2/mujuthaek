package kr.mujuthaek.api.notification;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

/**
 * 알림 테스트용 시계. 기본 2026-10-25 12:00 (한국)이라 혜택 픽스처(BenefitFixture, 신청 10/1~11/30)가 접수 중이에요. 실제 시계를 쓰면
 * 12월부터 마감돼 새 정책 알림 테스트가 깨져요. 테스트에서 시각을 옮길 수 있어요.
 */
@TestConfiguration(proxyBeanMethods = false)
public class NotificationTestClock {

  public static final ZoneId KOREA = ZoneId.of("Asia/Seoul");
  public static final String DEFAULT = "2026-10-25T12:00";

  @Bean
  @Primary
  MovableClock movableClock() {
    return new MovableClock();
  }

  public static final class MovableClock extends Clock {
    private volatile Instant now = korea(DEFAULT);

    public void set(String koreaDateTime) {
      now = korea(koreaDateTime);
    }

    @Override
    public ZoneId getZone() {
      return KOREA;
    }

    @Override
    public Clock withZone(ZoneId zone) {
      return this;
    }

    @Override
    public Instant instant() {
      return now;
    }
  }

  public static Instant korea(String dateTime) {
    return LocalDateTime.parse(dateTime).atZone(KOREA).toInstant();
  }
}
