package kr.mujuthaek.api.user.security;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.common.exception.Problems;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

/**
 * 보안 필터에서 나는 401·403도 GlobalExceptionHandler와 같은 Problem Details 모양으로 보내요 (common의 {@link
 * Problems}로 만들고 JSON 변환기로 써서 값이 이스케이프돼요).
 */
@Component
class ProblemResponses {

  private final JsonMapper json;

  ProblemResponses(JsonMapper json) {
    this.json = json;
  }

  void write(HttpServletRequest request, HttpServletResponse response, ErrorCode code)
      throws IOException {
    response.setStatus(code.status().value());
    response.setContentType(MediaType.APPLICATION_PROBLEM_JSON_VALUE);
    response.setCharacterEncoding(StandardCharsets.UTF_8.name());
    json.writeValue(response.getWriter(), Problems.of(code, code.message(), request));
  }
}
