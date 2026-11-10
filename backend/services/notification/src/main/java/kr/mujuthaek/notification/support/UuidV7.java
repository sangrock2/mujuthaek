package kr.mujuthaek.notification.support;

import java.security.SecureRandom;
import java.time.Clock;
import java.util.UUID;

/** 팀 규칙의 UUID v7 (앞 48비트가 밀리초 시각이라 만든 순서대로 정렬돼요). PostgreSQL 17에는 uuidv7()이 없어서 직접 만들어요. */
public final class UuidV7 {

  private static final SecureRandom RANDOM = new SecureRandom();

  private UuidV7() {}

  public static UUID next(Clock clock) {
    long millis = clock.millis();
    long high = (millis << 16) | 0x7000L | (RANDOM.nextInt() & 0x0FFFL);
    long low = (RANDOM.nextLong() & 0x3FFFFFFFFFFFFFFFL) | 0x8000000000000000L;
    return new UUID(high, low);
  }
}
