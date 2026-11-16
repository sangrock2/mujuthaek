package kr.mujuthaek.api.common.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.common.exception.Problems;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import tools.jackson.databind.json.JsonMapper;

/**
 * 주소의 검색 값에 NUL(%00)이 있으면 처리 전에 400이에요. 검색어·기관 이름 같은 값이 그대로 SQL 값으로 들어가는데, PostgreSQL은 NUL을 받지 않아서
 * 400이 아니라 DB 오류로 500과 운영 경보가 났어요(2026-11-16 보안 감사 L-12). 본문(JSON)의 글은 각 서비스가 {@code ControlChars}로
 * 봐요.
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class NulQueryFilter extends OncePerRequestFilter {

  private final JsonMapper json;

  public NulQueryFilter(JsonMapper json) {
    this.json = json;
  }

  @Override
  protected void doFilterInternal(
      HttpServletRequest request, HttpServletResponse response, FilterChain chain)
      throws ServletException, IOException {
    String query = request.getQueryString();
    if (query != null && query.toLowerCase(Locale.ROOT).contains("%00")) {
      ErrorCode code = ErrorCode.VALIDATION_FAILED;
      response.setStatus(code.status().value());
      response.setContentType(MediaType.APPLICATION_PROBLEM_JSON_VALUE);
      response.setCharacterEncoding(StandardCharsets.UTF_8.name());
      json.writeValue(
          response.getWriter(), Problems.of(code, "주소의 값에 쓸 수 없는 문자(NUL)가 있어요", request));
      return;
    }
    chain.doFilter(request, response);
  }
}
