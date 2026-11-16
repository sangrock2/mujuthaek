package kr.mujuthaek.api.chat.service;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.LongSupplier;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

/**
 * 좋아요·좋아요 취소의 회원별 횟수 제한 (1분에 {@link #LIKES_PER_MINUTE}번).
 *
 * <p>좋아요를 누르고 취소할 때마다 방 전체에 실시간으로 방송돼서, 계정 하나가 좋아요를 반복하면 그 방을 보는 모든 사람에게 이벤트를 쏟아낼 수 있었어요(2026-11-16
 * 보안 감사 L-11). 사람이 누르는 속도로는 닿지 않는 값이에요. 서버 한 대의 메모리에만 세요(개인 운영은 api가 한 대).
 */
@Component
public class ChatActionLimiter {

  static final int LIKES_PER_MINUTE = 30;
  static final long WINDOW_MS = 60_000;

  /** 이만큼 쌓이면 지난 창을 한 번에 치워요 (오래 안 쓴 회원 기록이 남지 않게) */
  private static final int SWEEP_AT = 10_000;

  private record Window(long startMs, int count) {}

  private final Map<UUID, Window> likes = new ConcurrentHashMap<>();
  private final LongSupplier clockMs;

  @Autowired
  public ChatActionLimiter() {
    this(System::currentTimeMillis);
  }

  ChatActionLimiter(LongSupplier clockMs) {
    this.clockMs = clockMs;
  }

  /** 이번 좋아요·취소를 해도 되면 true (센 다음이에요). 넘으면 false */
  public boolean tryLike(UUID userId) {
    long now = clockMs.getAsLong();
    if (likes.size() > SWEEP_AT) {
      likes.values().removeIf(w -> now - w.startMs() >= WINDOW_MS);
    }
    Window next =
        likes.compute(
            userId,
            (id, w) ->
                w == null || now - w.startMs() >= WINDOW_MS
                    ? new Window(now, 1)
                    : new Window(w.startMs(), w.count() + 1));
    return next.count() <= LIKES_PER_MINUTE;
  }

  /** 다시 할 수 있을 때까지 남은 초 (1 이상) */
  public long retryAfterSeconds(UUID userId) {
    Window w = likes.get(userId);
    if (w == null) {
      return 1;
    }
    long left = WINDOW_MS - (clockMs.getAsLong() - w.startMs());
    return Math.max(1, (left + 999) / 1000);
  }
}
