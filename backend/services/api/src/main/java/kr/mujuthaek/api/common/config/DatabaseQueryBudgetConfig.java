package kr.mujuthaek.api.common.config;

import java.time.Duration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.hibernate.autoconfigure.HibernatePropertiesCustomizer;
import org.springframework.boot.jdbc.autoconfigure.JdbcProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** API의 JDBC·JPA 조회 예산. DataSource 자체를 바꾸지 않아 Flyway와 별도 장기 적재에는 적용하지 않아요. */
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(JdbcProperties.class)
class DatabaseQueryBudgetConfig {
  @Bean
  HibernatePropertiesCustomizer jpaQueryBudget(JdbcProperties properties) {
    Duration timeout = properties.getTemplate().getQueryTimeout();
    // JdbcTemplate은 초, JPA는 밀리초예요. 1초 미만은 JDBC에서 0(무제한)으로 잘리므로 받지 않아요.
    if (timeout == null
        || timeout.compareTo(Duration.ofSeconds(1)) < 0
        || timeout.compareTo(Duration.ofMillis(Integer.MAX_VALUE)) > 0) {
      throw new IllegalArgumentException(
          "API_QUERY_TIMEOUT must be at least one second and fit JPA milliseconds");
    }
    int milliseconds = Math.toIntExact(timeout.toMillis());
    return values -> values.put("jakarta.persistence.query.timeout", milliseconds);
  }
}
