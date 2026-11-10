package kr.mujuthaek.api.area.geocode;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class CallLimiterTest {

  /** 기다리면 그만큼 시각이 가는 시계. */
  private static final class TestClock extends Clock {
    Instant now;

    TestClock(String at) {
      now = Instant.parse(at);
    }

    @Override
    public ZoneId getZone() {
      return ZoneOffset.UTC;
    }

    @Override
    public Clock withZone(ZoneId zone) {
      return Clock.fixed(now, zone);
    }

    @Override
    public Instant instant() {
      return now;
    }
  }

  private final List<Long> sleeps = new ArrayList<>();

  @Test
  void waitsWhenPerSecondIsFull() {
    var clock = new TestClock("2026-10-23T01:00:00Z");
    var limiter =
        new CallLimiter(
            2,
            100,
            clock,
            ms -> {
              sleeps.add(ms);
              clock.now = clock.now.plusMillis(ms);
            });

    assertThat(limiter.acquire()).isTrue();
    clock.now = clock.now.plusMillis(300);
    assertThat(limiter.acquire()).isTrue();
    assertThat(limiter.acquire()).isTrue(); // 첫 호출에서 1초가 지날 때까지 700ms 기다림
    assertThat(sleeps).containsExactly(700L);
    clock.now = clock.now.plus(Duration.ofSeconds(5));
    assertThat(limiter.acquire()).isTrue();
    assertThat(sleeps).hasSize(1);
  }

  @Test
  void dailyLimitResetsAtKoreanMidnight() {
    // 한국 시각 23:59:59
    var clock = new TestClock("2026-10-23T14:59:59Z");
    var limiter = new CallLimiter(10, 1, clock, sleeps::add);

    assertThat(limiter.acquire()).isTrue();
    assertThat(limiter.acquire()).isFalse();
    clock.now = clock.now.plusSeconds(1); // 한국 시각 다음 날 00:00:00
    assertThat(limiter.acquire()).isTrue();
  }

  @Test
  void rejectsZeroLimits() {
    assertThatThrownBy(() -> new CallLimiter(0, 1, Clock.systemUTC(), sleeps::add))
        .isInstanceOf(IllegalArgumentException.class);
  }
}
