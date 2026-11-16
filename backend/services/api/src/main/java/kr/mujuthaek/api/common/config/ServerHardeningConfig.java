package kr.mujuthaek.api.common.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.tomcat.TomcatConnectorCustomizer;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

/** 서버 앞단 심층 방어 (2026-11-16 보안 감사 4장). */
@Configuration
class ServerHardeningConfig {

  /**
   * Tomcat이 서블릿 6 명세의 「의심스러운 주소」를 400으로 막아요: {@code /..;/}처럼 경로 매개변수가 붙은 {@code .}·{@code ..}, 인코딩한
   * {@code %2e}·{@code %2f}, 매개변수만 있는 빈 구간 등. nginx가 원본 주소를 그대로 넘겨서 {@code /api/..;/internal/…}이
   * 들어올 수 있는데, 지금까지는 Spring Security의 StrictHttpFirewall 한 겹만 막고 있었어요.
   */
  @Bean
  TomcatConnectorCustomizer rejectSuspiciousUris() {
    return connector -> connector.setRejectSuspiciousURIs(true);
  }

  /**
   * {@code /actuator/prometheus}에만 거는 문지기({@link MetricsAccessFilter}). 서블릿 주소 매핑으로 걸어서 {@code ;}
   * 매개변수·중복 {@code /}가 붙은 주소도 같은 문지기를 지나요. 보안 필터(-100)보다 먼저 돌아요.
   *
   * @param token 지표를 읽는 Bearer 토큰 (METRICS_TOKEN). 비면 아래 requireToken을 따라요
   * @param requireToken 토큰이 없을 때 지표를 막을지 (운영 true)
   */
  @Bean
  FilterRegistrationBean<MetricsAccessFilter> metricsAccessFilter(
      @Value("${app.metrics.token:}") String token,
      @Value("${app.metrics.require-token:false}") boolean requireToken) {
    var registration = new FilterRegistrationBean<>(new MetricsAccessFilter(token, requireToken));
    registration.addUrlPatterns("/actuator/prometheus", "/actuator/prometheus/*");
    registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 5);
    return registration;
  }
}
