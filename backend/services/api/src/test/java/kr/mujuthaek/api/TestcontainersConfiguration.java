package kr.mujuthaek.api;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;

/** DB가 필요한 테스트용 PostgreSQL + PostGIS 컨테이너. {@code @Import}로 가져다 써요. */
@TestConfiguration(proxyBeanMethods = false)
public class TestcontainersConfiguration {

  private static final DockerImageName POSTGIS =
      DockerImageName.parse("postgis/postgis:17-3.5").asCompatibleSubstituteFor("postgres");

  @Bean
  @ServiceConnection
  PostgreSQLContainer postgres() {
    return new PostgreSQLContainer(POSTGIS);
  }
}
