package kr.mujuthaek.notification.delivery.email;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class MailPropertiesBindingTest {
  @Configuration(proxyBeanMethods = false)
  @EnableConfigurationProperties(MailProperties.class)
  static class PropertiesConfig {}

  private final ApplicationContextRunner context =
      new ApplicationContextRunner().withUserConfiguration(PropertiesConfig.class);

  @Test
  void nestedDefaultsBindWithTheCompatibilityConstructorPresent() {
    context.run(
        app -> {
          assertThat(app).hasNotFailed();
          var ses = app.getBean(MailProperties.class).ses();
          assertThat(ses.region()).isEqualTo("ap-northeast-2");
          assertThat(ses.configurationSet()).isEmpty();
        });
  }

  @Test
  void configuredSetBindsAndInvalidNamesFailStartup() {
    context
        .withPropertyValues("notification.mail.ses.configuration-set=mujuthaek-personal-delivery")
        .run(
            app -> {
              assertThat(app).hasNotFailed();
              assertThat(app.getBean(MailProperties.class).ses().configurationSet())
                  .isEqualTo("mujuthaek-personal-delivery");
            });
    context
        .withPropertyValues("notification.mail.ses.configuration-set=invalid/name")
        .run(app -> assertThat(app).hasFailed());
  }
}
