package kr.mujuthaek.api;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

// RabbitMQ 없이 뜨는지만 봐요. 수신기는 각 테스트에서 직접 불러요.
@SpringBootTest(properties = "spring.rabbitmq.listener.simple.auto-startup=false")
@Import(TestcontainersConfiguration.class)
class ApiApplicationTests {

  @Test
  void contextLoads() {}
}
