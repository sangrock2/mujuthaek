package kr.mujuthaek.api.traffic.controller;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.util.regex.Pattern;
import kr.mujuthaek.api.traffic.TrafficProperties;
import kr.mujuthaek.api.traffic.controller.spec.InternalTrafficApiSpec;
import kr.mujuthaek.api.traffic.dto.TrafficPageRequest;
import kr.mujuthaek.api.traffic.log.RequestClassifier;
import kr.mujuthaek.api.traffic.log.RequestLogStore;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 프론트 서버가 넘기는 화면 요청 (설명은 {@link InternalTrafficApiSpec}). */
@RestController
@RequestMapping("/api/internal/traffic")
class InternalTrafficController implements InternalTrafficApiSpec {

  /** IPv4·IPv6 글자만. 이상한 값은 버려요(해시·가리기에 그대로 쓰니까). */
  private static final Pattern IP = Pattern.compile("[0-9A-Fa-f:.]{2,45}");

  private final TrafficProperties props;
  private final RequestLogStore store;
  private final Clock clock;

  InternalTrafficController(TrafficProperties props, RequestLogStore store, Clock clock) {
    this.props = props;
    this.store = store;
    this.clock = clock;
  }

  @Override
  @PostMapping("/pages")
  public ResponseEntity<Void> page(
      @RequestHeader(name = "X-Traffic-Token", required = false) String token,
      @RequestBody TrafficPageRequest page) {
    if (!props.ingestEnabled()) {
      return ResponseEntity.notFound().build();
    }
    if (token == null
        || !MessageDigest.isEqual(
            token.getBytes(StandardCharsets.UTF_8),
            props.ingestToken().getBytes(StandardCharsets.UTF_8))) {
      return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
    }
    if (page == null || page.path() == null || !page.path().startsWith("/")) {
      return ResponseEntity.badRequest().build();
    }
    String ua = page.userAgent();
    String ip = page.ip() != null && IP.matcher(page.ip()).matches() ? page.ip() : null;
    store.add(
        new RequestLogStore.Entry(
            clock.instant(),
            "GET",
            RequestClassifier.normalizePath(page.path().split("[?#]", 2)[0]),
            null,
            null,
            RequestClassifier.client(ua),
            ua == null ? null : ua.substring(0, Math.min(200, ua.length())),
            ip,
            RequestClassifier.Area.PAGE,
            null));
    return ResponseEntity.accepted().build();
  }
}
