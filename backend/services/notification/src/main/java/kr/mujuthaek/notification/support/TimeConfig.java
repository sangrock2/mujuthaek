package kr.mujuthaek.notification.support;

import java.time.Clock;
import java.time.ZoneId;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

/** 시각 계산(조용한 시간·묶음 시각)은 모두 한국 시간이에요. 테스트에서 시각을 고정할 수 있게 Clock을 빈으로 둬요. */
@Configuration
@EnableScheduling
public class TimeConfig {

  public static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");

  @Bean
  Clock clock() {
    return Clock.system(SEOUL);
  }
}
