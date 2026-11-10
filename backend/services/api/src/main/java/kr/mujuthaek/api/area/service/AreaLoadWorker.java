package kr.mujuthaek.api.area.service;

import java.time.Duration;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import kr.mujuthaek.api.area.domain.AreaLoadReport;
import kr.mujuthaek.api.area.repository.AreaLoadQueue;
import kr.mujuthaek.api.common.alert.OpsAlert;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * area 적재 대기열(PENDING)을 하나씩 꺼내 적재해요. 메시지 수신과 떼어 두어서, 한 파일이 몇십 분 걸려도 RabbitMQ 소비자가 끊기지 않아요.
 *
 * <ul>
 *   <li>적재는 전용 스레드 하나에서 차례로 해요 (다른 {@code @Scheduled} 작업을 막지 않게). 같은 원천·범위는 적재기가 DB 잠금으로 한 번 더 막아요
 *   <li>수신기가 요청을 남기면 {@link #wake()}로 바로 깨우고, 놓친 요청은 30초마다 다시 봐요
 *   <li>S3·DB 연결 오류처럼 예외가 나면 1분·2분 뒤 다시 꺼내고, {@link AreaLoadQueue#MAX_ATTEMPTS}번이면 FAILED로 두고 알려요
 *   <li>api가 뜰 때 남아 있는 RUNNING(앞선 api가 멈추거나 꺼짐)은 FAILED로 닫고 다시 기다리게 넣어요 ({@link #run})
 * </ul>
 *
 * <p>끄려면 {@code mujuthaek.area.load.worker-enabled=false} (테스트·운영 명령).
 */
@Component
public class AreaLoadWorker implements ApplicationRunner {

  private static final Logger log = LoggerFactory.getLogger(AreaLoadWorker.class);
  static final String STALE_ERROR = "api가 멈추거나 꺼져 끝나지 못했어요";
  private static final Duration RETRY_STEP = Duration.ofMinutes(1);

  private final AreaLoadQueue queue;
  private final AreaSourceLoadService loads;
  private final OpsAlert alert;
  private final boolean enabled;
  private final ExecutorService executor =
      Executors.newSingleThreadExecutor(Thread.ofVirtual().name("area-load").factory());
  private final AtomicBoolean draining = new AtomicBoolean();

  public AreaLoadWorker(
      AreaLoadQueue queue,
      AreaSourceLoadService loads,
      OpsAlert alert,
      @Value("${mujuthaek.area.load.worker-enabled:true}") boolean enabled) {
    this.queue = queue;
    this.loads = loads;
    this.alert = alert;
    this.enabled = enabled;
  }

  /** 뜰 때 멈춘 기록부터 정리하고 대기열을 비우기 시작해요. */
  @Override
  public void run(ApplicationArguments args) {
    if (!enabled) {
      return;
    }
    recover();
    wake();
  }

  void recover() {
    List<AreaLoadQueue.Recovered> stale = queue.recoverStale(STALE_ERROR);
    if (stale.isEmpty()) {
      return;
    }
    StringBuilder detail = new StringBuilder();
    for (var s : stale) {
      detail
          .append(s.request().source())
          .append(' ')
          .append(s.request().scope())
          .append(" (")
          .append(s.attempts())
          .append("번째) → ")
          .append(s.requeued() ? "다시 기다림" : "더 하지 않음")
          .append('\n');
    }
    log.warn("멈춘 area 적재 {}건을 정리했어요\n{}", stale.size(), detail);
    alert.send("area.load.stale", "멈춘 area 적재 " + stale.size() + "건을 정리했어요", detail.toString());
  }

  /** 놓친 요청이 없게 30초마다 봐요. 이미 돌고 있으면 아무것도 안 해요. */
  @Scheduled(fixedDelay = 30_000, initialDelay = 30_000)
  void poll() {
    wake();
  }

  /** 대기열 비우기를 시작해요 (이미 돌고 있으면 그대로 둬요). */
  public void wake() {
    if (!enabled || !draining.compareAndSet(false, true)) {
      return;
    }
    executor.execute(
        () -> {
          try {
            drain();
          } finally {
            draining.set(false);
          }
        });
  }

  void drain() {
    try {
      for (Optional<AreaLoadQueue.Claimed> next = queue.claimNext();
          next.isPresent();
          next = queue.claimNext()) {
        loadOne(next.get());
      }
    } catch (RuntimeException e) {
      // 대기열을 읽지 못함(DB 연결 등): 다음 poll에서 다시 봐요
      log.warn("area 적재 대기열을 읽지 못했어요: {}", e.toString());
    }
  }

  void loadOne(AreaLoadQueue.Claimed job) {
    var r = job.request();
    String what = r.source() + " " + r.scope();
    try {
      AreaLoadReport report =
          loads.loadQueued(
              job.runId(),
              new AreaSourceLoadService.Command(
                  r.source(), r.scope(), r.fileKey(), r.sha256(), r.dataDate(), r.allowShrink()));
      if (report.status() == AreaLoadReport.Status.FAILED) {
        // 파일 문제(칸 없음, 잘린 파일 등)라 다시 해도 같아요
        alert.send("area.load.failed:" + r.source(), "area 적재 실패: " + what, report.error());
      }
    } catch (RuntimeException e) {
      boolean retry =
          queue.release(
              job.runId(), job.attempts(), e.toString(), RETRY_STEP.multipliedBy(job.attempts()));
      log.warn("area 적재 중 오류 {} ({}번째, 다시 {}): {}", what, job.attempts(), retry, e.toString());
      if (!retry) {
        alert.send(
            "area.load.error:" + r.source(),
            "area 적재를 " + job.attempts() + "번 해도 끝내지 못했어요: " + what,
            e.toString());
      }
    }
  }
}
