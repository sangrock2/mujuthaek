package kr.mujuthaek.api.common.cache;

import com.github.benmanes.caffeine.cache.Caffeine;
import com.github.benmanes.caffeine.cache.LoadingCache;
import java.time.Clock;
import java.time.Duration;
import java.util.concurrent.Executor;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.function.Function;

/**
 * 무거운 조회 결과를 키별로 잠깐(fresh) 다시 쓰는 캐시 (Caffeine).
 *
 * <ul>
 *   <li>처음이거나 오래 안 쓰여 비었으면 이 요청이 계산하고, 같은 키를 동시에 부른 요청은 그 결과를 기다려요(계산은 한 번).
 *   <li>fresh가 지난 뒤 처음 부르면 지난 값을 바로 주고 뒤에서 새로 계산해요. 그래서 만료 순간에도 아무도 계산을 기다리지 않아요.
 *   <li>계산이 실패하면 남기지 않아요(처음이면 오류를 그대로 던지고, 뒤에서 새로 계산하다 실패하면 지난 값을 계속 써요).
 *   <li>fresh의 10배 동안 아무도 안 부르면 비워요(오래된 값을 꺼내 주지 않게).
 * </ul>
 *
 * <p>관리자 화면처럼 여러 명이 같은 숫자를 자주 여는 곳에 써요(2026-10-29 부하 시험: 같은 집계를 매번 다시 돌려 DB가 포화됨).
 */
public final class RecentCache<K, V> {

  /** 뒤에서 새로 계산하는 일(DB·외부 API 대기)은 가상 스레드에서. */
  private static final Executor REFRESH = Executors.newVirtualThreadPerTaskExecutor();

  private final LoadingCache<K, V> cache;

  /**
   * @param fresh 이 시간 안에는 계산하지 않고 그대로 줘요
   * @param clock 시각(시험에서 바꿀 수 있게)
   * @param load 키 하나의 값을 계산해요
   */
  public RecentCache(Duration fresh, Clock clock, Function<K, V> load) {
    this.cache =
        Caffeine.newBuilder()
            .ticker(() -> TimeUnit.MILLISECONDS.toNanos(clock.millis()))
            .refreshAfterWrite(fresh)
            .expireAfterWrite(fresh.multipliedBy(10))
            .maximumSize(1_000)
            .executor(REFRESH)
            .build(load::apply);
  }

  public V get(K key) {
    return cache.get(key);
  }

  /** 모두 비워요(바뀐 것을 바로 보여야 할 때: 검수 처리 직후 등). 뒤에서 계산 중이던 값도 버려요. */
  public void clear() {
    cache.invalidateAll();
  }
}
