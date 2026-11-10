package kr.mujuthaek.api.notification.service.internal;

import java.net.URI;
import java.net.URISyntaxException;
import java.time.Clock;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.notification.repository.PushSubscriptionRepository;
import kr.mujuthaek.api.notification.repository.PushSubscriptionRepository.Device;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 웹 푸시 구독 기기 등록·해제 (contracts/schemas/web-push.draft.md 1·2장). 기기에 구독이 있으면 그 기기 푸시가 켜진 거예요 (따로 켬·끔
 * 설정은 없어요).
 *
 * <p>주소(endpoint)·키는 알면 그 기기에 알림을 보낼 수 있는 값이라 로그·오류 문구에 넣지 않아요. 로그에는 회원 ID와 푸시 서비스 도메인만 남겨요.
 */
@Service
public class PushSubscriptionService implements PushDeviceFinder {

  private static final Logger log = LoggerFactory.getLogger(PushSubscriptionService.class);

  static final int MAX_ENDPOINT_LENGTH = 2048;
  static final int MAX_USER_AGENT_LENGTH = 200;

  /** 내용 암호화 공개키: P-256 압축하지 않은 점 (0x04 + x + y) */
  static final int P256DH_BYTES = 65;

  /** 내용 암호화 비밀값 */
  static final int AUTH_BYTES = 16;

  private final PushSubscriptionRepository subscriptions;
  private final PushProperties properties;
  private final Clock clock;

  public PushSubscriptionService(
      PushSubscriptionRepository subscriptions, PushProperties properties, Clock clock) {
    this.subscriptions = subscriptions;
    this.properties = properties;
    this.clock = clock;
  }

  /** PWA가 구독할 때 쓰는 VAPID 공개키. 설정이 없으면 503이에요 */
  public String publicKey() {
    if (properties.vapidPublicKey().isBlank()) {
      throw new CustomException(ErrorCode.PUSH_NOT_CONFIGURED);
    }
    return properties.vapidPublicKey();
  }

  /**
   * 이 기기를 등록하거나 다시 등록해요. 다른 회원이 쓰던 주소면(같은 브라우저에서 다른 계정으로 로그인) 이 회원으로 옮겨요. 기기가 너무 많으면 가장 오래 안 쓴 기기를
   * 지워요.
   */
  @Transactional
  public void subscribe(
      UUID userId, String endpoint, String p256dh, String auth, String userAgent) {
    publicKey(); // 키가 없는데 받으면 보낼 수 없는 구독이 쌓여요
    String host = checkEndpoint(endpoint);
    checkKey("keys.p256dh", p256dh, P256DH_BYTES);
    checkKey("keys.auth", auth, AUTH_BYTES);

    Optional<UUID> owner = subscriptions.lockOwner(endpoint);
    subscriptions.upsert(userId, endpoint, p256dh, auth, label(userAgent), clock.instant());
    int evicted = subscriptions.keepLatest(userId, properties.maxDevices());

    if (owner.isEmpty()) {
      log.info("푸시 기기 등록: userId={}, host={}", userId, host);
    } else if (!owner.get().equals(userId)) {
      log.info("푸시 기기를 다른 회원에게서 옮김: userId={}, from={}, host={}", userId, owner.get(), host);
    }
    if (evicted > 0) {
      log.info("기기가 많아 오래된 푸시 기기를 지움: userId={}, 지운 수={}", userId, evicted);
    }
  }

  /** 이 기기 해제 (이 기기 알림 끄기, 로그아웃 직전). 없거나 다른 회원 기기여도 조용히 끝나요 */
  @Transactional
  public void unsubscribe(UUID userId, String endpoint) {
    if (subscriptions.deleteByEndpoint(userId, endpoint) > 0) {
      log.info("푸시 기기 해제: userId={}", userId);
    }
  }

  /**
   * 푸시 서비스가 죽었다고 한 기기를 지워요 (알림 서버의 push.subscription.expired). 그 회원의 그 주소만 지워서, 그사이 다른 회원으로 옮겨진 기기는
   * 남아요. 없으면 조용히 끝나요 (같은 이벤트가 두 번 와도 같아요).
   */
  @Transactional
  public void removeExpired(UUID userId, String endpoint, Integer status) {
    if (subscriptions.deleteByEndpoint(userId, endpoint) > 0) {
      log.info("죽은 푸시 기기를 지움: userId={}, status={}", userId, status);
    }
  }

  /** 내 기기 모두 해제 (모든 기기 알림 끄기, 탈퇴). 지운 수를 돌려줘요 */
  @Transactional
  public int unsubscribeAll(UUID userId) {
    int deleted = subscriptions.deleteAll(userId);
    if (deleted > 0) {
      log.info("푸시 기기 모두 해제: userId={}, 지운 수={}", userId, deleted);
    }
    return deleted;
  }

  /** 목록에서 고른 기기 해제. 내 기기가 아니면 404예요 (다른 회원 기기가 있는지 알려 주지 않아요) */
  @Transactional
  public void remove(UUID userId, UUID subscriptionId) {
    if (subscriptions.deleteById(userId, subscriptionId) == 0) {
      throw new CustomException(ErrorCode.PUSH_SUBSCRIPTION_NOT_FOUND);
    }
    log.info("푸시 기기 해제: userId={}, subscriptionId={}", userId, subscriptionId);
  }

  @Transactional(readOnly = true)
  public List<Device> devices(UUID userId) {
    return subscriptions.findDevices(userId);
  }

  /** 알림 요청에 실을 기기. 알림 요청을 적는 트랜잭션 안에서 불러요 (회원당 최근 {@code maxDevices}대) */
  @Override
  public Map<UUID, List<PushDevice>> latest(Collection<UUID> userIds) {
    Map<UUID, List<PushDevice>> byUser = new LinkedHashMap<>();
    for (var d : subscriptions.findLatestForSend(userIds, properties.maxDevices())) {
      byUser
          .computeIfAbsent(d.userId(), id -> new ArrayList<>())
          .add(new PushDevice(d.endpoint(), d.p256dh(), d.auth()));
    }
    return byUser;
  }

  /** https 주소이고 푸시 서비스 도메인이어야 해요. 그 도메인을 돌려줘요 (로그용) */
  private String checkEndpoint(String endpoint) {
    if (endpoint == null || endpoint.isBlank()) {
      throw invalid("endpoint", "꼭 있어야 해요");
    }
    if (endpoint.length() > MAX_ENDPOINT_LENGTH) {
      throw invalid("endpoint", MAX_ENDPOINT_LENGTH + "자를 넘어요");
    }
    URI uri;
    try {
      uri = new URI(endpoint);
    } catch (URISyntaxException e) {
      throw invalid("endpoint", "주소 형식이 아니에요");
    }
    if (!"https".equals(uri.getScheme()) || uri.getUserInfo() != null || uri.getPort() != -1) {
      throw invalid("endpoint", "https 푸시 서비스 주소여야 해요");
    }
    String host = uri.getHost();
    if (!properties.allows(host)) {
      throw invalid("endpoint", "지원하는 푸시 서비스 주소가 아니에요");
    }
    return host;
  }

  /** base64url이고 풀었을 때 길이가 맞아야 해요 (브라우저 subscription.toJSON() 모양) */
  private static void checkKey(String field, String value, int bytes) {
    if (value == null || value.isBlank()) {
      throw invalid(field, "꼭 있어야 해요");
    }
    byte[] decoded;
    try {
      decoded = Base64.getUrlDecoder().decode(value);
    } catch (IllegalArgumentException e) {
      throw invalid(field, "base64url 형식이 아니에요");
    }
    if (decoded.length != bytes) {
      throw invalid(field, "길이가 맞지 않아요");
    }
  }

  private static String label(String userAgent) {
    if (userAgent == null || userAgent.isBlank()) {
      return null;
    }
    String trimmed = userAgent.strip();
    return trimmed.length() <= MAX_USER_AGENT_LENGTH
        ? trimmed
        : trimmed.substring(0, MAX_USER_AGENT_LENGTH);
  }

  /** 오류 문구에는 칸 이름만 넣고 값은 넣지 않아요 */
  private static CustomException invalid(String field, String reason) {
    return new CustomException(ErrorCode.VALIDATION_FAILED, field + ": " + reason);
  }
}
