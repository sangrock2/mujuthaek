package kr.mujuthaek.api.common.logging;

import jakarta.servlet.http.HttpServletRequest;
import java.util.Set;
import org.springframework.web.servlet.HandlerMapping;
import org.springframework.web.util.pattern.PathPattern;

/** Bounded log metadata. Request paths may contain credentials, so log only the framework route. */
public final class LogText {
  private static final Set<String> METHODS =
      Set.of("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT");

  private LogText() {}

  public static String singleLine(String text, int limit) {
    if (text == null) return "";
    return text.substring(0, Math.min(text.length(), limit))
        .replace('\r', ' ')
        .replace('\n', ' ')
        .replaceAll("[\\p{Cc}\\p{Cf}\\p{Zl}\\p{Zp}]", " ");
  }

  public static String requestMethod(HttpServletRequest request) {
    String method = request.getMethod();
    return method != null && METHODS.contains(method) ? method : "OTHER";
  }

  public static String requestRoute(HttpServletRequest request) {
    Object matched = request.getAttribute(HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
    String route =
        matched instanceof PathPattern pattern
            ? pattern.getPatternString()
            : matched instanceof String pattern ? pattern : "[unmapped]";
    return singleLine(route, 256);
  }
}
