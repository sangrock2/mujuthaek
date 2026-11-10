package kr.mujuthaek.api.area.geocode;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.ArrayDeque;
import java.util.Deque;

/**
 * 외부 API 호출 수 제한: 초당 몇 번(넘으면 기다림), 하루(한국 시각) 몇 번(넘으면 그날은 안 부름). 재시도도 한 번으로 세요.
 *
 * <p>앱 하나 안에서만 세요. api를 여러 대 띄우면 설정 값을 대수로 나눠서 줘요.
 */
final class CallLimiter {

  private static final ZoneId KOREA = ZoneId.of("Asia/Seoul");
  private static final Duration WINDOW = Duration.ofSeconds(1);

  private final int perSecond;
  private final int perDay;
  private final Clock clock;
  private final JusoSearchClient.Sleeper sleeper;
  private final Deque<Instant> recent = new ArrayDeque<>();
  private LocalDate day;
  private int today;

  CallLimiter(int perSecond, int perDay, Clock clock, JusoSearchClient.Sleeper sleeper) {
    if (perSecond < 1 || perDay < 1) {
      throw new IllegalArgumentException("호출 수 제한은 1 이상이어야 해요");
    }
    this.perSecond = perSecond;
    this.perDay = perDay;
    this.clock = clock;
    this.sleeper = sleeper;
  }

  /** 부를 수 있으면 한 번 세고 true. 하루 한도를 넘었으면 세지 않고 false. 초당 한도면 자리가 날 때까지 기다려요. */
  synchronized boolean acquire() {
    LocalDate now = LocalDate.now(clock.withZone(KOREA));
    if (!now.equals(day)) {
      day = now;
      today = 0;
    }
    if (today >= perDay) {
      return false;
    }
    if (recent.size() >= perSecond) {
      Duration since = Duration.between(recent.peekFirst(), clock.instant());
      if (since.compareTo(WINDOW) < 0) {
        sleeper.sleep(WINDOW.minus(since).toMillis());
      }
      recent.pollFirst();
    }
    recent.addLast(clock.instant());
    today++;
    return true;
  }
}
