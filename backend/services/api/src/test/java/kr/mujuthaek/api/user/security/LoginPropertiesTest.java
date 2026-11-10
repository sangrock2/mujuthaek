package kr.mujuthaek.api.user.security;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;

class LoginPropertiesTest {

  @Test
  void frontendUrlOnlyWhenNoExtraOrigins() {
    var props = new LoginProperties("http://localhost:3000", null);
    assertThat(props.allowedOrigins()).containsExactly("http://localhost:3000");
  }

  @Test
  void extraOriginsAddedWithoutBlanksOrDuplicates() {
    var props =
        new LoginProperties(
            "http://localhost:3000",
            List.of(
                "http://localhost:3200",
                "",
                " https://preview.mujuthaek.kr ",
                "http://localhost:3000"));
    assertThat(props.allowedOrigins())
        .containsExactly(
            "http://localhost:3000", "http://localhost:3200", "https://preview.mujuthaek.kr");
  }
}
