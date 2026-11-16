package kr.mujuthaek.notification.delivery.email;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * 인증 메일을 받는 주소별·전체 상한 (서버 메모리, 서버 한 대 기준이라 다시 띄우면 처음부터 세요).
 *
 * <p>api는 계정마다 1분에 한 번·하루 5번으로 막지만, 계정을 여러 개 만들면 한 주소로 공식 인증 메일을 계속 보낼 수 있었어요. 남의 받은편지함에 메일을 쏟아붓거나
 * SES 한도·평판(반송·스팸 신고)을 소진해 모든 메일을 멈추지 못하게 해요(2026-11-16 보안 감사 M-3).
 */
@Component
class VerificationMailLimiter {

  private static final Duration HOUR = Duration.ofHours(1);
  private static final Duration DAY = Duration.ofDays(1);
  private static final int SWEEP_ABOVE = 5_000;

  private final Clock clock;
  private final int perAddressHour;
  private final int perAddressDay;
  private final int globalHour;
  private final Map<String, Deque<Instant>> byAddress = new HashMap<>();
  private final Deque<Instant> global = new ArrayDeque<>();

  VerificationMailLimiter(
      Clock clock,
      @Value("${notification.mail.verification.per-address-hour:3}") int perAddressHour,
      @Value("${notification.mail.verification.per-address-day:10}") int perAddressDay,
      @Value("${notification.mail.verification.global-hour:120}") int globalHour) {
    this.clock = clock;
    this.perAddressHour = perAddressHour;
    this.perAddressDay = perAddressDay;
    this.globalHour = globalHour;
  }

  /** 보내도 되면 보낸 것으로 기록하고 true. 상한을 넘으면 기록하지 않고 false. */
  synchronized boolean tryAcquire(String address) {
    Instant now = clock.instant();
    prune(global, now.minus(HOUR));
    String key = address.toLowerCase(Locale.ROOT);
    Deque<Instant> sent = byAddress.getOrDefault(key, new ArrayDeque<>());
    prune(sent, now.minus(DAY));
    long lastHour = sent.stream().filter(at -> at.isAfter(now.minus(HOUR))).count();
    if (global.size() >= globalHour || sent.size() >= perAddressDay || lastHour >= perAddressHour) {
      return false;
    }
    if (byAddress.size() > SWEEP_ABOVE) {
      byAddress.values().forEach(times -> prune(times, now.minus(DAY)));
      byAddress.values().removeIf(Deque::isEmpty);
    }
    sent.addLast(now);
    byAddress.put(key, sent);
    global.addLast(now);
    return true;
  }

  private static void prune(Deque<Instant> times, Instant before) {
    while (!times.isEmpty() && !times.peekFirst().isAfter(before)) {
      times.pollFirst();
    }
  }
}
