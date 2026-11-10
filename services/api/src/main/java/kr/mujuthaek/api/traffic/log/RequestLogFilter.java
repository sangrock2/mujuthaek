package kr.mujuthaek.api.traffic.log;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.time.Clock;
import java.time.Instant;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.util.UrlPathHelper;

/**
 * api 서버 요청을 기록해요(보안 필터보다 바깥에서 돌아 401·403까지 셉니다). 회원 ID·쿼리 문자열·요청 본문은 남기지 않아요. 상태 확인(/actuator)과
 * CORS 사전 요청(OPTIONS)은 빼요. 원본 IP는 {@code request.getRemoteAddr()}만 써요(운영에서 프록시 뒤라면
 * server.forward-headers-strategy로 믿을 수 있는 프록시의 X-Forwarded-For만 반영하게 설정해요. 헤더를 그대로 믿으면 IP를 속일 수
 * 있어요). 운영은 Vercel → nginx(:80) 구성이라 nginx를 바로 부르면 X-Forwarded-For를 속일 수 있어요(Vercel 나가는 IP가 정해져 있지
 * 않아 앱에서는 막지 못함). 기록의 IP는 참고 값이에요.
 */
public class RequestLogFilter extends OncePerRequestFilter {

  private final RequestLogStore store;
  private final Clock clock;

  public RequestLogFilter(RequestLogStore store, Clock clock) {
    this.store = store;
    this.clock = clock;
  }

  /**
   * 앱 안의 주소(문맥 경로를 뺀 것, 디코딩하지 않음). 전달 헤더(X-Forwarded-Prefix)는 요청 주소 앞에 문맥 경로를 붙일 뿐이라 이 값은 바뀌지 않아요.
   * 예전엔 요청 주소를 그대로 봐서 「X-Forwarded-Prefix: /actuator」로 /actuator 요청처럼 꾸며 기록에서 빠질 수 있었어요 (2026-11-10
   * 코드 검토). 보안 설정의 경로 판정도 이 값을 써요.
   */
  private static String path(HttpServletRequest request) {
    return UrlPathHelper.rawPathInstance.getPathWithinApplication(request);
  }

  @Override
  protected boolean shouldNotFilter(HttpServletRequest request) {
    String path = path(request);
    return "OPTIONS".equals(request.getMethod())
        || path.startsWith("/actuator")
        || path.startsWith("/api/internal/traffic/") // 프론트 서버가 넘기는 화면 요청은 따로 기록해요
        || !(path.startsWith("/api/")
            || path.startsWith("/login/oauth2/")
            || path.startsWith("/oauth2/"));
  }

  @Override
  protected void doFilterInternal(
      HttpServletRequest request, HttpServletResponse response, FilterChain chain)
      throws ServletException, IOException {
    Instant start = clock.instant();
    try {
      chain.doFilter(request, response);
    } finally {
      String path = path(request);
      String ua = request.getHeader("User-Agent");
      store.add(
          new RequestLogStore.Entry(
              start,
              request.getMethod(),
              RequestClassifier.normalizePath(path),
              response.getStatus(),
              (int) Math.min(Integer.MAX_VALUE, clock.millis() - start.toEpochMilli()),
              RequestClassifier.client(ua),
              ua == null ? null : ua.substring(0, Math.min(200, ua.length())),
              request.getRemoteAddr(),
              RequestClassifier.area(path),
              RequestClassifier.loginResult(path, response.getHeader("Location"))));
    }
  }
}
