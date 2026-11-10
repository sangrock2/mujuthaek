package kr.mujuthaek.api.common.id;

import java.security.SecureRandom;
import java.util.UUID;

/** UUID v7 (RFC 9562): 앞 48비트가 밀리초 시각이라 만든 순서대로 정렬돼요. API의 모든 ID가 이 형식이에요. */
public final class UuidV7 {

  private static final SecureRandom RANDOM = new SecureRandom();
  private static long lastMillis;
  private static long sequence;

  private UuidV7() {}

  /** 같은 밀리초 안에서도 만든 순서가 유지되게 12비트 순번을 써요. */
  public static synchronized UUID next() {
    long now = System.currentTimeMillis();
    if (now <= lastMillis) {
      sequence++;
      if (sequence > 0xFFF) { // 순번이 넘치면 다음 밀리초로
        lastMillis++;
        sequence = 0;
      }
      now = lastMillis;
    } else {
      lastMillis = now;
      sequence = 0;
    }
    long msb = (now << 16) | 0x7000L | sequence;
    long lsb = (RANDOM.nextLong() & 0x3FFFFFFFFFFFFFFFL) | 0x8000000000000000L;
    return new UUID(msb, lsb);
  }
}
