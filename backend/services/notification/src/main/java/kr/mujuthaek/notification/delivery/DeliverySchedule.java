package kr.mujuthaek.notification.delivery;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalTime;
import java.time.ZonedDateTime;
import java.util.List;
import java.util.Optional;
import kr.mujuthaek.notification.support.TimeConfig;
import org.springframework.stereotype.Component;

/** 보낼 시각 규칙 (contracts/schemas/notification-tables.draft.md 3-2). 모두 한국 시간이에요. */
@Component
public class DeliverySchedule {

  /** 묶음 메일 시각. 둘 다 조용한 시간(22:00~08:00) 밖이에요 */
  static final List<LocalTime> DIGEST_TIMES = List.of(LocalTime.of(8, 0), LocalTime.of(18, 0));

  static final LocalTime QUIET_START = LocalTime.of(22, 0);
  static final LocalTime QUIET_END = LocalTime.of(8, 0);

  /** 실패한 뒤 다시 보낼 때까지 기다리는 시간. 다 쓰면 FAILED */
  static final List<Duration> RETRY_DELAYS =
      List.of(Duration.ofMinutes(1), Duration.ofMinutes(5), Duration.ofMinutes(30));

  private final Clock clock;

  public DeliverySchedule(Clock clock) {
    this.clock = clock;
  }

  public Instant now() {
    return clock.instant();
  }

  /** 바로 보내는 줄의 처음 보낼 시각. 지금, 조용한 시간이면 다음 08:00 */
  public Instant firstAttempt(boolean quietEnabled) {
    ZonedDateTime now = ZonedDateTime.now(clock).withZoneSameInstant(TimeConfig.SEOUL);
    return quietEnabled && isQuiet(now) ? nextQuietEnd(now).toInstant() : now.toInstant();
  }

  /**
   * 묶음 줄의 처음 보낼 시각. 같은 묶음의 줄이 모두 같은 시각을 가져야 한 번에 나가서, 정해진 칸(08:00·18:00, 정각·30분)에 맞춰요.
   *
   * <ul>
   *   <li>{@link DigestCadence#TWICE_A_DAY}: 다음 08:00 또는 18:00 (조용한 시간 밖이라 따로 미루지 않아요)
   *   <li>{@link DigestCadence#EVERY_30_MINUTES}: 다음 정각 또는 30분. 그 칸이 조용한 시간이고 회원이 켰으면 다음 08:00
   * </ul>
   */
  public Instant firstDigest(DigestCadence cadence, boolean quietEnabled) {
    ZonedDateTime now = ZonedDateTime.now(clock).withZoneSameInstant(TimeConfig.SEOUL);
    return switch (cadence) {
      case TWICE_A_DAY -> nextDigest(now).toInstant();
      case EVERY_30_MINUTES -> {
        ZonedDateTime slot = nextHalfHour(now);
        yield (quietEnabled && isQuiet(slot) ? nextQuietEnd(slot) : slot).toInstant();
      }
    };
  }

  /** 지금이 조용한 시간이면 다음 08:00, 아니면 비어 있어요. 보내기 직전에 다시 확인해요 (그사이 설정을 켰을 수 있어요) */
  public Optional<Instant> postponeForQuiet(boolean quietEnabled) {
    ZonedDateTime now = ZonedDateTime.now(clock).withZoneSameInstant(TimeConfig.SEOUL);
    return quietEnabled && isQuiet(now)
        ? Optional.of(nextQuietEnd(now).toInstant())
        : Optional.empty();
  }

  /** {@code attempts}번 실패한 뒤 다시 보낼 시각. 재시도를 다 썼으면 비어 있어요 */
  public Optional<Instant> retryAt(int attempts) {
    if (attempts < 1 || attempts > RETRY_DELAYS.size()) {
      return Optional.empty();
    }
    return Optional.of(clock.instant().plus(RETRY_DELAYS.get(attempts - 1)));
  }

  private static ZonedDateTime nextDigest(ZonedDateTime now) {
    for (LocalTime time : DIGEST_TIMES) {
      ZonedDateTime candidate = now.with(time).withSecond(0).withNano(0);
      if (!candidate.isBefore(now)) {
        return candidate;
      }
    }
    return now.plusDays(1).with(DIGEST_TIMES.getFirst()).withSecond(0).withNano(0);
  }

  /** 지금이 딱 정각·30분이면 지금, 아니면 다음 정각·30분 */
  private static ZonedDateTime nextHalfHour(ZonedDateTime now) {
    ZonedDateTime slot = now.withMinute(now.getMinute() < 30 ? 0 : 30).withSecond(0).withNano(0);
    return slot.isBefore(now) ? slot.plusMinutes(30) : slot;
  }

  private static boolean isQuiet(ZonedDateTime now) {
    LocalTime time = now.toLocalTime();
    return !time.isBefore(QUIET_START) || time.isBefore(QUIET_END);
  }

  private static ZonedDateTime nextQuietEnd(ZonedDateTime now) {
    ZonedDateTime today = now.with(QUIET_END).withSecond(0).withNano(0);
    return today.isAfter(now) ? today : today.plusDays(1);
  }
}
