package kr.mujuthaek.api.common.logging;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.servlet.HandlerMapping;
import org.springframework.web.util.pattern.PathPatternParser;

class LogTextTest {
  @Test
  void untrustedPathAndMethodCannotBecomeLogMetadata() {
    var request = new MockHttpServletRequest("EVIL\r\nENTRY", "/private-secret\nFORGED");
    assertThat(LogText.requestMethod(request)).isEqualTo("OTHER");
    assertThat(LogText.requestRoute(request)).isEqualTo("[unmapped]");
    request.setAttribute(
        HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE,
        new PathPatternParser().parse("/api/notices/{id}"));
    assertThat(LogText.requestRoute(request)).isEqualTo("/api/notices/{id}");
  }

  @Test
  void exceptionMessagesStayBoundedAndCannotForgeAnotherLogLine() {
    String input = "failed\r\nFORGED\u001b[31m\u0085\u2028\u2029\u202e" + "x".repeat(5000);
    String safe = LogText.singleLine(input, 256);
    assertThat(safe)
        .hasSize(256)
        .doesNotContain("\r", "\n", "\u001b", "\u0085", "\u2028", "\u2029", "\u202e");
    assertThat(SensitiveFields.masked(new IllegalStateException(input)).getMessage())
        .doesNotContain("\r", "\n", "\u2028", "\u001b");
  }

  @Test
  void cyclicExceptionCausesDoNotBreakTheErrorHandler() {
    var first = new IllegalStateException("first");
    var second = new IllegalStateException("second", first);
    first.initCause(second);
    Throwable safe = SensitiveFields.masked(first);
    assertThat(safe.getCause().getCause().getMessage()).isEqualTo("[cause chain truncated]");
  }
}
