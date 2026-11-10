package kr.mujuthaek.notification.delivery.push;

import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.regex.Pattern;
import kr.mujuthaek.notification.delivery.Channel;
import kr.mujuthaek.notification.delivery.DeliveryException;
import kr.mujuthaek.notification.delivery.DigestCadence;
import kr.mujuthaek.notification.delivery.NotificationChannel;
import kr.mujuthaek.notification.delivery.OutgoingNotification;
import kr.mujuthaek.notification.notification.NotificationRequest;
import kr.mujuthaek.notification.notification.NotificationRequest.PushDevice;
import kr.mujuthaek.notification.notification.NotificationType;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.json.JsonMapper;

/**
 * 웹 푸시 채널 (contracts/schemas/web-push.draft.md 4장). 받을 곳은 요청의 recipients[].push(api가 넣은 구독 기기
 * 목록)이고, 발송 줄 하나에서 기기마다 보내요.
 *
 * <ul>
 *   <li>새 공고·새 정책은 30분마다 모아서, 2건 이상이면 "새 소식 N건" 한 번으로 보내요
 *   <li>받았거나 죽은 기기(404·410)는 빼고, 일시적으로 못 보낸 기기만 남겨 다시 보내요 (이미 받은 기기가 두 번 받지 않게). 죽은 기기는
 *       push.subscription.expired로 api에 알려요
 *   <li>모든 기기가 죽었으면 FAILED {@code ALL_EXPIRED}. VAPID 키 문제(401·403)는 모든 발송이 실패하는 설정 오류라 경고 로그
 *   <li>기기가 여러 대면 동시에 보내요 (느린 푸시 서비스 하나가 다른 기기를 늦추지 않게)
 * </ul>
 *
 * <p>기기 주소·키·내용은 로그·오류에 넣지 않아요. 로그에는 푸시 서비스 도메인과 응답 코드만 남겨요.
 */
@Component
@EnableConfigurationProperties(PushProperties.class)
class PushChannel implements NotificationChannel {

  private static final Logger log = LoggerFactory.getLogger(PushChannel.class);

  /** api가 넣는 최대 기기 수. 더 오면 앞의 것만 써요 */
  static final int MAX_DEVICES = 5;

  static final int MAX_TITLE = 100;
  static final int MAX_BODY = 200;

  /** JSON 목록 안 알림함 ID 하나의 크기: 따옴표 둘·쉼표 하나·UUID 36자. */
  private static final int ID_BYTES = 39;

  /** 새 소식 묶음을 누르면 가는 화면 (여러 건이라 한 공고로 보낼 수 없어서 알림함으로) */
  static final String INBOX_PATH = "/notifications";

  /** api 문구 앞머리 ("새 공고: ", "새 정책: " 등). 묶음 본문에서는 빼요 */
  private static final Pattern NEW_PREFIX = Pattern.compile("^새 [^:]{1,10}: ");

  private static final TypeReference<List<PushDevice>> DEVICES = new TypeReference<>() {};

  private final PushSender sender;
  private final PushProperties properties;
  private final JsonMapper json;
  private final ExpiredSubscriptions expired;

  PushChannel(
      PushSender sender, PushProperties properties, JsonMapper json, ExpiredSubscriptions expired) {
    this.sender = sender;
    this.properties = properties;
    this.json = json;
    this.expired = expired;
  }

  @Override
  public Channel channel() {
    return Channel.PUSH;
  }

  /** 보낼 수 있는 기기만 JSON 목록으로. 하나도 없으면 비어 있어서 발송 줄을 만들지 않아요 */
  @Override
  public Optional<String> address(NotificationRequest.Recipient recipient) {
    if (recipient.push() == null) {
      return Optional.empty();
    }
    List<PushDevice> devices =
        recipient.push().stream().filter(this::usable).limit(MAX_DEVICES).toList();
    if (devices.size() < Math.min(recipient.push().size(), MAX_DEVICES)) {
      log.warn("보낼 수 없는 푸시 기기를 뺐어요: userId={}", recipient.userId());
    }
    return devices.isEmpty() ? Optional.empty() : Optional.of(write(devices));
  }

  @Override
  public Optional<DigestCadence> digestCadence() {
    return Optional.of(DigestCadence.EVERY_30_MINUTES);
  }

  @Override
  public String send(UUID userId, String address, List<OutgoingNotification> notifications)
      throws DeliveryException {
    List<PushDevice> devices = read(address);
    boolean deliveredBefore = deliveredBefore(address); // 앞 차례에 다른 기기가 이미 받았는지(다시 보낼 기기만 남긴 받을 곳)
    OutgoingNotification first = notifications.getFirst();
    byte[] payload = payload(notifications);
    if (payload.length > WebPushCrypto.MAX_PLAINTEXT_BYTES) {
      throw new DeliveryException("PUSH_PAYLOAD_TOO_LARGE", true);
    }
    Duration ttl = ttl(first.type(), notifications.size() > 1);
    String urgency = first.type() == NotificationType.DEADLINE_D1 ? "high" : "normal";

    List<PushDevice> remaining = new ArrayList<>();
    int delivered = 0;
    int dead = 0;
    String retryCode = null;
    String failCode = null;
    String authCode = null;
    Duration retryAfter = null;
    List<PushDevice> usable = new ArrayList<>();
    for (PushDevice device : devices) {
      if (usable(device)) {
        usable.add(device);
      } else {
        failCode = "PUSH_ENDPOINT_NOT_ALLOWED";
      }
    }
    List<Sent> results = sendAll(usable, payload, ttl, urgency);
    for (Sent sent : results) {
      PushDevice device = sent.device();
      String host = host(device.endpoint());
      if (sent.response() == null) {
        remaining.add(device);
        retryCode = "PUSH_IO";
        log.debug("푸시 서비스에 닿지 않음: host={}, error={}", host, sent.error());
        continue;
      }
      PushResponse response = sent.response();
      int status = response.status();
      if (status >= 200 && status < 300) {
        delivered++;
      } else if (status == 404 || status == 410) {
        dead++; // 앱 삭제·권한 끔·만료. api에 알려 구독을 지워요
        this.expired.report(userId, device.endpoint(), status);
        log.info("죽은 푸시 구독이라 뺐어요 (api에 알림): userId={}, host={}, status={}", userId, host, status);
      } else if (status == 401 || status == 403) {
        log.warn("푸시 서비스가 VAPID 서명을 거절했어요 (키 설정 확인): host={}, status={}", host, status);
        authCode = "PUSH_" + status;
      } else if (status == 429 || status >= 500) {
        remaining.add(device);
        retryCode = "PUSH_" + status;
        retryAfter = longer(retryAfter, response.retryAfter());
      } else {
        failCode = "PUSH_" + status; // 400·413 등: 우리 쪽 형식·크기 문제라 다시 보내도 같아요
        log.warn("푸시 서비스가 요청을 거절했어요: host={}, status={}", host, status);
      }
    }
    // 한 대라도 받았으면 보낸 것이에요(계약 web-push.draft.md). 예전엔 기기 하나의 401·403이 다른 기기의 재시도·수신을 보기 전에 묶음
    // 전체를 영구 실패로 던졌고, 앞 차례에 받은 기기가 있어도 남은 기기가 죽으면 FAILED였어요(2026-11-10 코드 검토)
    boolean anyDelivered = deliveredBefore || delivered > 0;
    if (!remaining.isEmpty()) {
      throw new DeliveryException(
          retryCode, write(remaining, anyDelivered), retryAfter, anyDelivered);
    }
    if (anyDelivered) {
      return null; // 푸시 서비스는 메시지 ID를 따로 주지 않아요 (Location 헤더뿐)
    }
    if (authCode != null) {
      throw new DeliveryException(authCode, true); // 키 설정 오류: 다시 보내도 모두 실패해요
    }
    throw new DeliveryException(failCode != null ? failCode : "ALL_EXPIRED", true);
  }

  /** 기기 한 대에 보낸 결과. 연결 실패면 response가 null */
  private record Sent(PushDevice device, PushResponse response, String error) {}

  /** 기기마다 동시에 보내요 (가상 스레드). 결과는 기기 순서대로예요 */
  private List<Sent> sendAll(
      List<PushDevice> devices, byte[] payload, Duration ttl, String urgency) {
    if (devices.size() == 1) {
      return List.of(sendOne(devices.getFirst(), payload, ttl, urgency));
    }
    try (ExecutorService pool = Executors.newVirtualThreadPerTaskExecutor()) {
      List<Future<Sent>> futures =
          devices.stream().map(d -> pool.submit(() -> sendOne(d, payload, ttl, urgency))).toList();
      List<Sent> results = new ArrayList<>();
      for (int i = 0; i < futures.size(); i++) {
        try {
          results.add(futures.get(i).get());
        } catch (ExecutionException e) {
          results.add(new Sent(devices.get(i), null, e.getCause().getClass().getSimpleName()));
        } catch (InterruptedException e) {
          Thread.currentThread().interrupt();
          results.add(new Sent(devices.get(i), null, "InterruptedException"));
        }
      }
      return results;
    }
  }

  private Sent sendOne(PushDevice device, byte[] payload, Duration ttl, String urgency) {
    try {
      return new Sent(device, sender.send(new PushMessage(device, payload, ttl, urgency)), null);
    } catch (IOException e) {
      return new Sent(device, null, e.getClass().getSimpleName());
    }
  }

  /** 서비스 워커가 받을 내용 (event.data.json()) */
  byte[] payload(List<OutgoingNotification> notifications) {
    Map<String, Object> body = new LinkedHashMap<>();
    body.put("v", 1);
    if (notifications.size() == 1) {
      OutgoingNotification n = notifications.getFirst();
      body.put("type", n.type().name());
      body.put("title", cut(n.title(), MAX_TITLE));
      body.put("body", cut(n.body(), MAX_BODY));
      body.put("linkPath", n.linkPath());
      body.put("tag", n.linkPath()); // 같은 화면 알림은 기기에서 최신 것 하나로
    } else {
      String rest = " 외 " + (notifications.size() - 1) + "건";
      String headline = NEW_PREFIX.matcher(notifications.getFirst().title()).replaceFirst("");
      body.put("type", "NEW_DIGEST");
      body.put("title", "새 소식 " + notifications.size() + "건");
      body.put("body", cut(headline, MAX_BODY - rest.length()) + rest);
      body.put("linkPath", INBOX_PATH);
      body.put("tag", INBOX_PATH);
    }
    // 기기가 「떴어요·눌렀어요」를 api에 알릴 알림함 줄 ID (묶음이면 묶인 알림 모두)
    List<UUID> ids =
        notifications.stream()
            .map(OutgoingNotification::inboxId)
            .filter(java.util.Objects::nonNull)
            .toList();
    body.put("ids", ids);
    byte[] bytes = json.writeValueAsString(body).getBytes(StandardCharsets.UTF_8);
    // 묶음이 크면(한 칸에 90건 남짓) ID 목록만으로 한도를 넘어요. 예전엔 묶음 전체를 PUSH_PAYLOAD_TOO_LARGE로 실패해 그 회원이
    // 푸시를 하나도 못 받았어요(2026-11-10 코드 검토). 알림은 보내고, 한도에 맞을 만큼만 ID를 넣어요(빠진 줄은 「떴어요」 기록만 없음)
    int keep = ids.size();
    while (bytes.length > WebPushCrypto.MAX_PLAINTEXT_BYTES && keep > 0) {
      int over = bytes.length - WebPushCrypto.MAX_PLAINTEXT_BYTES;
      keep = Math.max(0, keep - (over + ID_BYTES - 1) / ID_BYTES);
      body.put("ids", ids.subList(0, keep));
      bytes = json.writeValueAsString(body).getBytes(StandardCharsets.UTF_8);
    }
    return bytes;
  }

  /** 기기가 꺼져 있을 때 푸시 서비스가 들고 있을 시간. 늦게 받으면 틀린 말이 되는 마감 알림은 짧게 */
  static Duration ttl(NotificationType type, boolean digest) {
    if (digest) {
      return Duration.ofHours(24);
    }
    return switch (type) {
      case DEADLINE_D1 -> Duration.ofHours(12);
      case DEADLINE_D3 -> Duration.ofHours(48);
      case NEW_NOTICE, NEW_SUPPORT -> Duration.ofHours(24);
      case CORRECTED, FOLLOW_UP, REPORT_ANSWERED -> Duration.ofHours(72);
    };
  }

  /** https이고, 푸시 서비스 도메인이고, 키가 있는 기기 (api에서도 같은 검사를 해요) */
  private boolean usable(PushDevice device) {
    if (device == null
        || blank(device.endpoint())
        || blank(device.p256dh())
        || blank(device.auth())) {
      return false;
    }
    try {
      URI uri = new URI(device.endpoint());
      return "https".equals(uri.getScheme())
          && uri.getUserInfo() == null
          && uri.getPort() == -1
          && properties.allows(uri.getHost());
    } catch (java.net.URISyntaxException e) {
      return false;
    }
  }

  private String write(List<PushDevice> devices) {
    return json.writeValueAsString(devices);
  }

  /**
   * 다시 보낼 받을 곳. 이미 받은 기기가 있으면 {"delivered":true,"devices":[...]}로 그 사실을 남겨, 다음 차례가 남은 기기만 실패해도 보낸
   * 것으로 적어요. 없으면 예전처럼 기기 목록 그대로.
   */
  private String write(List<PushDevice> devices, boolean delivered) {
    if (!delivered) {
      return write(devices);
    }
    Map<String, Object> wrapped = new LinkedHashMap<>();
    wrapped.put("delivered", true);
    wrapped.put("devices", devices);
    return json.writeValueAsString(wrapped);
  }

  private List<PushDevice> read(String address) throws DeliveryException {
    try {
      if (address.stripLeading().startsWith("{")) {
        return json.readValue(json.readTree(address).path("devices").toString(), DEVICES);
      }
      return json.readValue(address, DEVICES);
    } catch (JacksonException e) {
      throw new DeliveryException("PUSH_ADDRESS_UNREADABLE", true);
    }
  }

  private boolean deliveredBefore(String address) {
    return address.stripLeading().startsWith("{")
        && json.readTree(address).path("delivered").asBoolean(false);
  }

  private static Duration longer(Duration current, Duration other) {
    if (other == null) {
      return current;
    }
    return current == null || other.compareTo(current) > 0 ? other : current;
  }

  private static String host(String endpoint) {
    try {
      return new URI(endpoint).getHost();
    } catch (java.net.URISyntaxException | NullPointerException e) {
      return null;
    }
  }

  /** 글자 수(코드 포인트)로 자르고 끝에 … */
  static String cut(String value, int max) {
    String oneLine = value.replaceAll("[\\r\\n]+", " ").strip();
    if (oneLine.codePointCount(0, oneLine.length()) <= max) {
      return oneLine;
    }
    return oneLine.substring(0, oneLine.offsetByCodePoints(0, max - 1)) + "…";
  }

  private static boolean blank(String value) {
    return value == null || value.isBlank();
  }
}
