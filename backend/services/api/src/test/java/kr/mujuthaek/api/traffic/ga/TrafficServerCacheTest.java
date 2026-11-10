package kr.mujuthaek.api.traffic.ga;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;
import kr.mujuthaek.api.traffic.TrafficProperties;
import kr.mujuthaek.api.traffic.dto.BotTrafficResponse;
import kr.mujuthaek.api.traffic.log.RequestLogStore;
import kr.mujuthaek.api.traffic.service.TrafficService;
import org.junit.jupiter.api.Test;
import org.springframework.web.client.RestClient;

/** 트래픽 서버 숫자(요청 기록 집계)는 1분 동안 다시 쓰고, 같은 기간을 동시에 열어도 집계는 한 번만 해요. */
class TrafficServerCacheTest {

  private static final Instant NOW = Instant.parse("2026-10-29T03:00:00Z");

  /** 시험에서 시각을 앞으로 옮길 수 있는 시계. */
  private static final class MovableClock extends Clock {
    private volatile Instant now = NOW;

    void plus(Duration d) {
      now = now.plus(d);
    }

    @Override
    public ZoneId getZone() {
      return ZoneOffset.UTC;
    }

    @Override
    public Clock withZone(ZoneId zone) {
      return this;
    }

    @Override
    public Instant instant() {
      return now;
    }
  }

  private final MovableClock clock = new MovableClock();
  private final RequestLogStore logs = mock(RequestLogStore.class);
  private final AtomicInteger dailyCalls = new AtomicInteger();
  private final AtomicInteger botCalls = new AtomicInteger();

  private TrafficService service() {
    // GA 설정 없음: 서버 숫자만 봐요
    var props =
        new TrafficProperties(
            "salt",
            14,
            90,
            "",
            new TrafficProperties.Ga("", "", Duration.ofHours(1), Duration.ofSeconds(5)));
    var ga = new GaDataClient(props.ga(), RestClient.builder(), clock, "http://ga.test");
    when(logs.daily(any(), any()))
        .thenAnswer(
            i -> {
              dailyCalls.incrementAndGet();
              return List.of();
            });
    when(logs.clientsDaily(any(), any()))
        .thenAnswer(
            i -> {
              botCalls.incrementAndGet();
              Thread.sleep(200); // 느린 집계: 그동안 들어온 요청은 이걸 기다려야 해요
              return List.of();
            });
    when(logs.topSources(any(), any(), anyInt())).thenReturn(List.of());
    when(logs.topBotPaths(any(), any(), anyInt())).thenReturn(List.of());
    when(logs.statuses(any(), any())).thenReturn(List.of());
    when(logs.adminAccess(any(), any(), anyInt())).thenReturn(List.of());
    when(logs.loginFailures(any(), any(), anyInt())).thenReturn(List.of());
    return new TrafficService(ga, logs, props, clock);
  }

  @Test
  void 서버_숫자는_1분_안에는_다시_세지_않고_지나면_지난_값을_주며_뒤에서_다시_센다() throws Exception {
    var service = service();

    BotTrafficResponse first = service.bots(7);
    clock.plus(Duration.ofSeconds(59));
    assertThat(service.bots(7)).isSameAs(first);
    service.traffic(7);
    service.traffic(7);
    assertThat(botCalls).hasValue(1);
    assertThat(dailyCalls).hasValue(1);

    clock.plus(Duration.ofSeconds(2)); // 처음 집계부터 1분 넘음
    // 지난 값을 바로 주고(기다리지 않음) 뒤에서 새로 세요
    assertThat(service.bots(7)).isSameAs(first);
    BotTrafficResponse next = waitForNew(() -> service.bots(7), first);
    assertThat(next).isNotSameAs(first);
    assertThat(botCalls).hasValue(2);
    // 기간이 다르면 따로 세요
    service.bots(30);
    assertThat(botCalls).hasValue(3);
  }

  /** 뒤에서 새로 센 값이 들어올 때까지 (최대 3초). */
  private static <T> T waitForNew(java.util.function.Supplier<T> read, T old)
      throws InterruptedException {
    for (int i = 0; i < 60; i++) {
      T now = read.get();
      if (now != old) {
        return now;
      }
      Thread.sleep(50);
    }
    return read.get();
  }

  @Test
  void 같은_기간을_동시에_열어도_집계는_한_번() throws Exception {
    var service = service();
    var pool = Executors.newFixedThreadPool(20);
    var start = new CountDownLatch(1);
    List<Future<BotTrafficResponse>> results = new ArrayList<>();
    for (int i = 0; i < 20; i++) {
      results.add(
          pool.submit(
              () -> {
                start.await();
                return service.bots(7);
              }));
    }
    start.countDown();
    BotTrafficResponse first = results.get(0).get();
    for (var r : results) {
      assertThat(r.get()).isSameAs(first);
    }
    pool.shutdown();
    assertThat(botCalls).hasValue(1);
  }

  @Test
  void 집계가_실패하면_남기지_않고_다음_요청이_다시_센다() {
    var service = service();
    when(logs.clientsDaily(any(), any()))
        .thenThrow(new IllegalStateException("DB 끊김"))
        .thenReturn(List.of());

    assertThatThrownBy(() -> service.bots(7)).isInstanceOf(IllegalStateException.class);
    assertThat(service.bots(7).clients()).isEmpty();
  }

  @Test
  void GA_보고서가_만료된_순간_여럿이_열어도_GA는_한_번만_부른다() throws Exception {
    var props =
        new TrafficProperties(
            "salt",
            14,
            90,
            "",
            new TrafficProperties.Ga(
                "123", "key.json", Duration.ofHours(1), Duration.ofSeconds(5)));
    var ga = mock(GaDataClient.class);
    var gaCalls = new AtomicInteger();
    when(ga.configured()).thenReturn(true);
    when(ga.run(any(), anyInt()))
        .thenAnswer(
            i -> {
              gaCalls.incrementAndGet();
              Thread.sleep(200); // GA가 느린 동안 들어온 요청은 이걸 기다려요
              return java.util.Collections.nCopies(11, List.<GaDataClient.Row>of());
            });
    when(logs.daily(any(), any())).thenReturn(List.of());
    var service = new TrafficService(ga, logs, props, clock);

    var pool = Executors.newFixedThreadPool(20);
    var start = new CountDownLatch(1);
    List<Future<?>> results = new ArrayList<>();
    for (int i = 0; i < 20; i++) {
      results.add(
          pool.submit(
              () -> {
                start.await();
                return service.traffic(7).ga();
              }));
    }
    start.countDown();
    Object first = results.get(0).get();
    for (var r : results) {
      assertThat(r.get()).isSameAs(first);
    }
    pool.shutdown();
    assertThat(gaCalls).hasValue(1);

    // 한 시간이 지나면 다시 물어요. 그때 GA가 실패하면 지난 값을 보여 줘요
    clock.plus(Duration.ofMinutes(61));
    when(ga.run(any(), anyInt())).thenThrow(new IllegalStateException("GA 한도"));
    assertThat(service.traffic(7).ga()).isSameAs(first);
  }
}
