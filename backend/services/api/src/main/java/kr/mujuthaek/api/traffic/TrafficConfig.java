package kr.mujuthaek.api.traffic;

import java.time.Clock;
import kr.mujuthaek.api.traffic.log.RequestLogFilter;
import kr.mujuthaek.api.traffic.log.RequestLogStore;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration
@EnableConfigurationProperties(TrafficProperties.class)
class TrafficConfig {

  /** 보안 필터(-100)보다 먼저 돌아 거절된 요청(401·403)도 셉니다. */
  @Bean
  FilterRegistrationBean<RequestLogFilter> requestLogFilter(RequestLogStore store, Clock clock) {
    var registration = new FilterRegistrationBean<>(new RequestLogFilter(store, clock));
    registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
    registration.addUrlPatterns("/*");
    return registration;
  }
}
