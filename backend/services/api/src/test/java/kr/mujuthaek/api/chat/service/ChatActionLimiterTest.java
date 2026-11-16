package kr.mujuthaek.api.chat.service;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;

/** 좋아요·취소는 회원마다 1분에 30번까지 (2026-11-16 보안 감사 L-11). */
class ChatActionLimiterTest {

  private final AtomicLong now = new AtomicLong(1_000_000);
  private final ChatActionLimiter limiter = new ChatActionLimiter(now::get);

  @Test
  void thirtyPerMinuteThenRefusedUntilTheWindowEnds() {
    UUID me = UUID.randomUUID();
    for (int i = 0; i < ChatActionLimiter.LIKES_PER_MINUTE; i++) {
      assertThat(limiter.tryLike(me)).isTrue();
    }
    assertThat(limiter.tryLike(me)).isFalse();
    assertThat(limiter.retryAfterSeconds(me)).isBetween(1L, 60L);
    assertThat(limiter.tryLike(UUID.randomUUID())).as("다른 회원은 따로 세요").isTrue();

    now.addAndGet(ChatActionLimiter.WINDOW_MS);
    assertThat(limiter.tryLike(me)).isTrue();
  }
}
