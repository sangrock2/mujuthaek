package kr.mujuthaek.api.area.service;

import jakarta.annotation.PreDestroy;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import kr.mujuthaek.api.area.repository.NoticeLocationJobs;
import kr.mujuthaek.api.area.repository.NoticeLocationJobs.Job;
import kr.mujuthaek.api.common.alert.OpsAlert;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Component
public class NoticeLocationJobWorker {
  private static final Logger log = LoggerFactory.getLogger(NoticeLocationJobWorker.class);
  private final NoticeLocationJobs jobs;
  private final NoticeAreaLinkService link;
  private final OpsAlert alert;
  private final TransactionTemplate transaction;
  private final boolean enabled;
  private final AtomicBoolean working = new AtomicBoolean();
  private final ExecutorService executor =
      Executors.newSingleThreadExecutor(Thread.ofVirtual().name("notice-location-jobs").factory());

  public NoticeLocationJobWorker(
      NoticeLocationJobs jobs,
      NoticeAreaLinkService link,
      OpsAlert alert,
      PlatformTransactionManager transactionManager,
      @Value("${mujuthaek.area.location-worker-enabled:true}") boolean enabled) {
    this.jobs = jobs;
    this.link = link;
    this.alert = alert;
    this.transaction = new TransactionTemplate(transactionManager);
    this.enabled = enabled;
  }

  @Scheduled(fixedDelay = 5_000, initialDelay = 2_000)
  void poll() {
    if (!enabled || !working.compareAndSet(false, true)) {
      return;
    }
    executor.execute(
        () -> {
          try {
            jobs.claim().ifPresent(this::process);
          } catch (RuntimeException error) {
            log.warn("공고 위치 대기열 확인 실패: {}", error.getClass().getSimpleName());
          } finally {
            working.set(false);
          }
        });
  }

  void process(Job job) {
    var event = job.event();
    try {
      var resolved =
          link.resolve(
              event,
              () -> {
                if (!jobs.renew(job)) {
                  throw new Replaced();
                }
              });
      boolean stored =
          Boolean.TRUE.equals(
              transaction.execute(
                  status -> {
                    if (!jobs.lockCurrent(job)) {
                      jobs.finish(job);
                      return false;
                    }
                    link.store(event, resolved);
                    return true;
                  }));
      if (stored) {
        transaction.executeWithoutResult(
            status -> {
              if (jobs.lockCurrent(job)) {
                link.refresh(event);
              }
              jobs.finish(job);
            });
      }
    } catch (Replaced ignored) {
      // The newer publication or another claimant already owns the job.
    } catch (RuntimeException error) {
      String kind = error.getClass().getSimpleName();
      int failures = jobs.retry(job, kind);
      if (failures > 0) {
        log.warn(
            "공고 위치 처리 실패 noticeId={} version={} failures={} cause={}",
            event.noticeId(),
            event.noticeVersion(),
            failures,
            kind);
      }
      if (failures == 5) {
        alert.send(
            "area.notice-location-job.failed",
            "공고 위치 자동 처리 중단",
            "공고 " + event.noticeId() + " v" + event.noticeVersion() + " " + kind);
      }
    }
  }

  @PreDestroy
  void stop() {
    executor.shutdownNow();
  }

  private static final class Replaced extends RuntimeException {}
}
