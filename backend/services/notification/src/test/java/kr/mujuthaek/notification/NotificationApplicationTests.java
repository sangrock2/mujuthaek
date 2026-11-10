package kr.mujuthaek.notification;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

@SpringBootTest
@Import(TestcontainersConfiguration.class)
class NotificationApplicationTests {

  @Test
  void contextLoads() {}
}
