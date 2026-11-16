package kr.mujuthaek.api.common.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.springframework.http.HttpHeaders;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * {@code /actuator/prometheus} 문지기. 지표 포트는 호스트의 127.0.0.1에만 열려 있지만, 같은 컨테이너 망 안의 다른 컨테이너(문서 파서 포함)는
 * {@code api:8080}으로 바로 닿아서 지표를 읽을 수 있었어요(2026-11-16 보안 감사 4장).
 *
 * <ul>
 *   <li>토큰(METRICS_TOKEN)이 있으면 {@code Authorization: Bearer <토큰>}이 맞을 때만 열어요. 틀리면 401이에요
 *   <li>토큰이 없으면: 운영처럼 {@code requireToken}이 켜져 있으면 404(꺼 둔 것처럼), 아니면(로컬·테스트) 그대로 열어요
 * </ul>
 *
 * <p>{@code /actuator/health}는 이 문지기를 지나지 않아요(nginx·compose 헬스 체크·배포 스크립트가 써요).
 */
public final class MetricsAccessFilter extends OncePerRequestFilter {

  private static final String BEARER = "Bearer ";

  private final byte[] token;
  private final boolean requireToken;

  public MetricsAccessFilter(String token, boolean requireToken) {
    this.token = (token == null ? "" : token.strip()).getBytes(StandardCharsets.UTF_8);
    this.requireToken = requireToken;
  }

  @Override
  protected void doFilterInternal(
      HttpServletRequest request, HttpServletResponse response, FilterChain chain)
      throws ServletException, IOException {
    if (token.length == 0) {
      if (requireToken) {
        response.setStatus(HttpServletResponse.SC_NOT_FOUND);
        return;
      }
      chain.doFilter(request, response);
      return;
    }
    if (!MessageDigest.isEqual(token, presented(request))) {
      response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
      response.setHeader(HttpHeaders.WWW_AUTHENTICATE, "Bearer");
      return;
    }
    chain.doFilter(request, response);
  }

  private static byte[] presented(HttpServletRequest request) {
    String header = request.getHeader(HttpHeaders.AUTHORIZATION);
    if (header == null || !header.regionMatches(true, 0, BEARER, 0, BEARER.length())) {
      return new byte[0];
    }
    return header.substring(BEARER.length()).strip().getBytes(StandardCharsets.UTF_8);
  }
}
