package kr.mujuthaek.api.common.config;

import java.time.Clock;
import java.time.ZoneId;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** "오늘"은 서울 날짜예요 (접수 상태·D-day). 테스트는 고정 시계를 넣어요. */
@Configuration
class ClockConfig {

  static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");

  @Bean
  Clock clock() {
    return Clock.system(SEOUL);
  }
}
