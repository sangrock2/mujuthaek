package kr.mujuthaek.api.area.service;

import jakarta.annotation.PreDestroy;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import kr.mujuthaek.api.area.repository.PostgresNoticeLocations;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/** 공고가 다시 발행되지 않아도 주소 검색 실패를 작은 묶음으로 재조회해요. */
@Component
@ConditionalOnProperty(
    name = "mujuthaek.area.geocode.retry-enabled",
    havingValue = "true",
    matchIfMissing = true)
class NoticeGeocodeRetryWorker {
  private static final Logger log = LoggerFactory.getLogger(NoticeGeocodeRetryWorker.class);
  private static final int BATCH_SIZE = 5;

  private final PostgresNoticeLocations locations;
  private final AddressLocator locator;
  private final NoticeAreaLinkService link;
  private final AtomicBoolean running = new AtomicBoolean();
  private final ExecutorService executor =
      Executors.newSingleThreadExecutor(Thread.ofVirtual().name("notice-geocode-retry").factory());

  NoticeGeocodeRetryWorker(
      PostgresNoticeLocations locations, AddressLocator locator, NoticeAreaLinkService link) {
    this.locations = locations;
    this.locator = locator;
    this.link = link;
  }

  @Scheduled(fixedDelay = 900_000, initialDelay = 60_000)
  void poll() {
    if (!running.compareAndSet(false, true)) {
      return;
    }
    executor.execute(
        () -> {
          try {
            retryDue();
          } catch (RuntimeException e) {
            log.warn("공고 좌표 자동 재조회 실패: {}", e.getClass().getSimpleName());
          } finally {
            running.set(false);
          }
        });
  }

  void retryDue() {
    for (int i = 0; i < BATCH_SIZE; i++) {
      var next = locations.claimGeocodeRetry();
      if (next.isEmpty()) {
        return;
      }
      var retry = next.get();
      try {
        var result = locator.locate(retry.location().address(), retry.location().bjdCode());
        link.completeGeocodeRetry(retry, result);
      } catch (RuntimeException e) {
        log.warn(
            "공고 좌표 재조회 실패 locationId={}: {}", retry.locationId(), e.getClass().getSimpleName());
      }
    }
  }

  @PreDestroy
  void stop() {
    executor.shutdownNow();
  }
}
