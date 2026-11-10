package kr.mujuthaek.notification;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.rabbitmq.RabbitMQContainer;
import org.testcontainers.utility.DockerImageName;

/** 테스트용 PostgreSQL·RabbitMQ 컨테이너 (로컬 infra와 같은 이미지). {@code @Import}로 가져다 써요. */
@TestConfiguration(proxyBeanMethods = false)
public class TestcontainersConfiguration {

  private static final DockerImageName POSTGIS =
      DockerImageName.parse("postgis/postgis:17-3.5").asCompatibleSubstituteFor("postgres");

  @Bean
  @ServiceConnection
  PostgreSQLContainer postgres() {
    return new PostgreSQLContainer(POSTGIS);
  }

  @Bean
  @ServiceConnection
  RabbitMQContainer rabbitmq() {
    return new RabbitMQContainer(DockerImageName.parse("rabbitmq:4.1-management"));
  }
}
