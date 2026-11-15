package kr.mujuthaek.notification.delivery.email;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.yaml.snakeyaml.Yaml;

class MailConfigurationTest {
  @Test
  void applicationYamlLoadsWithConsentCheckUnderMailSettings() throws Exception {
    try (var stream = getClass().getResourceAsStream("/application.yml")) {
      Map<?, ?> root = new Yaml().load(stream);
      Map<?, ?> notification = (Map<?, ?>) root.get("notification");
      Map<?, ?> mail = (Map<?, ?>) notification.get("mail");
      assertThat(mail.get("consent-api-url"))
          .isEqualTo("${NOTIFICATION_MAIL_CONSENT_API_URL:http://localhost:8080}");
    }
  }
}
