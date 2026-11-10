package kr.mujuthaek.notification.delivery;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Instant;
import java.time.ZonedDateTime;
import kr.mujuthaek.notification.support.TimeConfig;
import org.junit.jupiter.api.Test;

class DeliveryScheduleTest {

  @Test
  void emailDigestGoesToNextEightOrSixPm() {
    assertThat(at("2026-10-23T07:59").firstDigest(DigestCadence.TWICE_A_DAY, false))
        .isEqualTo(seoul("2026-10-23T08:00"));
    assertThat(at("2026-10-23T08:00").firstDigest(DigestCadence.TWICE_A_DAY, false))
        .isEqualTo(seoul("2026-10-23T08:00"));
    assertThat(at("2026-10-23T10:00").firstDigest(DigestCadence.TWICE_A_DAY, false))
        .isEqualTo(seoul("2026-10-23T18:00"));
    assertThat(at("2026-10-23T18:01").firstDigest(DigestCadence.TWICE_A_DAY, true))
        .isEqualTo(seoul("2026-10-24T08:00"));
  }

  @Test
  void pushDigestGoesToNextHalfHour() {
    assertThat(at("2026-10-23T10:07").firstDigest(DigestCadence.EVERY_30_MINUTES, false))
        .isEqualTo(seoul("2026-10-23T10:30"));
    assertThat(at("2026-10-23T10:30").firstDigest(DigestCadence.EVERY_30_MINUTES, false))
        .as("딱 30분이면 그 칸")
        .isEqualTo(seoul("2026-10-23T10:30"));
    assertThat(at("2026-10-23T10:31").firstDigest(DigestCadence.EVERY_30_MINUTES, false))
        .isEqualTo(seoul("2026-10-23T11:00"));
    assertThat(at("2026-10-23T23:40").firstDigest(DigestCadence.EVERY_30_MINUTES, false))
        .as("날을 넘어가요")
        .isEqualTo(seoul("2026-10-24T00:00"));
  }

  @Test
  void pushDigestInQuietHoursWaitsUntilEightOnlyWhenOn() {
    assertThat(at("2026-10-23T21:40").firstDigest(DigestCadence.EVERY_30_MINUTES, true))
        .as("22:00 칸은 조용한 시간")
        .isEqualTo(seoul("2026-10-24T08:00"));
    assertThat(at("2026-10-23T21:20").firstDigest(DigestCadence.EVERY_30_MINUTES, true))
        .isEqualTo(seoul("2026-10-23T21:30"));
    assertThat(at("2026-10-24T03:10").firstDigest(DigestCadence.EVERY_30_MINUTES, true))
        .isEqualTo(seoul("2026-10-24T08:00"));
    assertThat(at("2026-10-24T07:40").firstDigest(DigestCadence.EVERY_30_MINUTES, true))
        .isEqualTo(seoul("2026-10-24T08:00"));
    assertThat(at("2026-10-23T23:10").firstDigest(DigestCadence.EVERY_30_MINUTES, false))
        .isEqualTo(seoul("2026-10-23T23:30"));
  }

  @Test
  void immediateWaitsUntilEightOnlyWhenQuietHoursOn() {
    assertThat(at("2026-10-23T23:00").firstAttempt(true)).isEqualTo(seoul("2026-10-24T08:00"));
    assertThat(at("2026-10-24T03:00").firstAttempt(true)).isEqualTo(seoul("2026-10-24T08:00"));
    assertThat(at("2026-10-23T23:00").firstAttempt(false)).isEqualTo(seoul("2026-10-23T23:00"));
    assertThat(at("2026-10-23T21:59").firstAttempt(true)).isEqualTo(seoul("2026-10-23T21:59"));
  }

  @Test
  void retriesThreeTimesThenStops() {
    DeliverySchedule schedule = at("2026-10-23T10:00");
    assertThat(schedule.retryAt(1)).contains(seoul("2026-10-23T10:01"));
    assertThat(schedule.retryAt(2)).contains(seoul("2026-10-23T10:05"));
    assertThat(schedule.retryAt(3)).contains(seoul("2026-10-23T10:30"));
    assertThat(schedule.retryAt(4)).isEmpty();
  }

  private static DeliverySchedule at(String localDateTime) {
    return new DeliverySchedule(Clock.fixed(seoul(localDateTime), TimeConfig.SEOUL));
  }

  private static Instant seoul(String localDateTime) {
    return ZonedDateTime.parse(localDateTime + ":00+09:00[Asia/Seoul]").toInstant();
  }
}
