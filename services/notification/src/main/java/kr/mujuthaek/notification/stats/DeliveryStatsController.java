package kr.mujuthaek.notification.stats;

import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletRequestWrapper;
import jakarta.servlet.http.HttpServletRequest;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Duration;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * api만 부르는 내부 API: 최근 발송 결과 합계 (관리자 「알림」 화면). 회원·주소·문구는 주지 않고 종류·채널별 숫자와 실패 사유만 줘요.
 *
 * <p>NOTIFICATION_INTERNAL_TOKEN이 있으면 같은 값의 Bearer 토큰만, 없으면 같은 컴퓨터에서 온 요청만 받아요.
 */
@RestController
class DeliveryStatsController {

  static final int MAX_DAYS = 90;

  private final JdbcClient jdbc;
  private final Clock clock;
  private final String token;

  DeliveryStatsController(
      JdbcClient jdbc, Clock clock, @Value("${notification.internal.token:}") String token) {
    this.jdbc = jdbc;
    this.clock = clock;
    this.token = token;
  }

  /**
   * 최근 {@code days}일에 만든 발송 줄의 결과.
   *
   * @return {days, byType[{type, channel, sent, failed, pending}], failures[{channel, error,
   *     count}]}
   */
  @GetMapping("/internal/stats")
  ResponseEntity<Map<String, Object>> stats(
      @RequestParam(defaultValue = "7") int days, HttpServletRequest request) {
    if (!allowed(request)) {
      return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
    }
    if (days < 1 || days > MAX_DAYS) {
      return ResponseEntity.badRequest().build();
    }
    var since = clock.instant().minus(Duration.ofDays(days)).atOffset(ZoneOffset.UTC);
    List<Map<String, Object>> byType =
        jdbc.sql(
                """
                select type, channel,
                       count(*) filter (where status = 'SENT') as sent,
                       count(*) filter (where status = 'FAILED') as failed,
                       count(*) filter (where status = 'PENDING') as pending
                  from deliveries
                 where created_at >= :since
                 group by type, channel
                 order by type, channel
                """)
            .param("since", since)
            .query(
                (rs, i) -> {
                  Map<String, Object> m = new LinkedHashMap<>();
                  m.put("type", rs.getString("type"));
                  m.put("channel", rs.getString("channel"));
                  m.put("sent", rs.getLong("sent"));
                  m.put("failed", rs.getLong("failed"));
                  m.put("pending", rs.getLong("pending"));
                  return m;
                })
            .list();
    // 실패 사유는 채널이 남긴 코드 (HTTP_410·TIMEOUT …)라 개인정보가 없어요
    List<Map<String, Object>> failures =
        jdbc.sql(
                """
                select channel, coalesce(last_error, 'UNKNOWN') as error, count(*) as count
                  from deliveries
                 where created_at >= :since and status = 'FAILED'
                 group by 1, 2
                 order by count desc, 1, 2
                 limit 20
                """)
            .param("since", since)
            .query(
                (rs, i) -> {
                  Map<String, Object> m = new LinkedHashMap<>();
                  m.put("channel", rs.getString("channel"));
                  m.put("error", rs.getString("error"));
                  m.put("count", rs.getLong("count"));
                  return m;
                })
            .list();
    Map<String, Object> body = new LinkedHashMap<>();
    body.put("days", days);
    body.put("byType", byType);
    body.put("failures", failures);
    return ResponseEntity.ok(body);
  }

  private boolean allowed(HttpServletRequest request) {
    if (token != null && !token.isBlank()) {
      String header = request.getHeader(HttpHeaders.AUTHORIZATION);
      return header != null
          && MessageDigest.isEqual(
              header.getBytes(StandardCharsets.UTF_8),
              ("Bearer " + token).getBytes(StandardCharsets.UTF_8));
    }
    try {
      return InetAddress.getByName(socketAddress(request)).isLoopbackAddress();
    } catch (UnknownHostException e) {
      return false;
    }
  }

  /**
   * 전달 헤더(X-Forwarded-For·Forwarded)로 바뀌지 않은 실제 연결 주소. 운영은 forward-headers-strategy=framework라
   * getRemoteAddr()가 호출자가 보낸 헤더 값이 되어, 같은 망의 다른 컨테이너가 「X-Forwarded-For: 127.0.0.1」로 같은 컴퓨터인 척할 수
   * 있었어요(2026-11-10 코드 검토). 감싼 요청을 벗겨 서블릿 컨테이너가 본 주소를 봐요.
   */
  static String socketAddress(HttpServletRequest request) {
    ServletRequest raw = request;
    while (raw instanceof ServletRequestWrapper wrapper) {
      raw = wrapper.getRequest();
    }
    return raw.getRemoteAddr();
  }
}
