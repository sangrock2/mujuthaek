package kr.mujuthaek.api.eligibility.service;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.api.common.event.NoticePublished;
import kr.mujuthaek.api.common.event.NoticeUpdated;
import kr.mujuthaek.api.eligibility.mapper.JudgmentReader;
import kr.mujuthaek.api.eligibility.rule.Judgment;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import kr.mujuthaek.api.notice.service.NoticeQueryService.JudgingSource;
import kr.mujuthaek.api.notice.service.NoticeQueryService.UnitPrice;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Service;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * 공고 판정 틀 캐시 (공고 ID·버전 → 판정 모델). 맞춤 목록·홈 요약은 요청마다 후보 최대 300개를 판정해서, 판정 틀을 매번 읽고 풀면 느려요.
 *
 * <p>판정 틀은 payload의 JSON 그대로가 아니라 읽어 둔 판정 모델(JudgmentReader)로 담아요. 2026-11-01 로컬 더미 공고 1,000개로 잰 값:
 * JSON 그대로 한 개 53.5KB, 판정 모델 4.4KB(12분의 1). 그래서 공고 1만 개를 다 담아도 50MB 안쪽이고, 판정할 때마다 JSON을 다시 읽지 않아요(한
 * 개 17~45µs). 기본 크기 2만 개({@code mujuthaek.judging.cache-size}).
 *
 * <p>공고가 바뀌면 버전이 달라져 키가 바뀌므로 옛 값은 쓰지 않아요(오래된 순으로 밀려나요). 뜰 때 열린 공고를 미리 채우고, 공고가 공개·수정되면 그 공고를 다시
 * 채워요. 적중률은 {@code mujuthaek_judging_cache_total{cache="notice", result="hit|miss"}}로 내보내요. 공개 데이터만
 * 담아요(사용자 조건·판정 결과는 담지 않아요).
 */
@Service
public class JudgingFrames {

  private static final Logger log = LoggerFactory.getLogger(JudgingFrames.class);
  private static final int PREWARM_CHUNK = 300;

  /** 판정에 쓰는 공고 내용 (판정 틀은 읽어 둔 모델, 없으면 null). */
  public record Frame(
      UUID noticeId,
      String field,
      String noticeType,
      Judgment judgment,
      List<UnitPrice> unitTypes,
      boolean eligibilityComplete) {

    public static Frame of(JudgingSource s) {
      return new Frame(
          s.noticeId(),
          s.field(),
          s.noticeType(),
          s.judgment() == null ? null : JudgmentReader.read(s.judgment()),
          s.unitTypes(),
          s.eligibilityComplete());
    }
  }

  private record Key(UUID id, int version) {}

  private final NoticeQueryService notices;
  private final int capacity;
  private final boolean prewarm;
  private final Counter hits;
  private final Counter misses;
  private final Map<Key, Frame> cache;

  public JudgingFrames(
      NoticeQueryService notices,
      MeterRegistry meters,
      @Value("${mujuthaek.judging.cache-size:20000}") int capacity,
      @Value("${mujuthaek.judging.prewarm:true}") boolean prewarm) {
    this.notices = notices;
    this.capacity = capacity;
    this.prewarm = prewarm;
    this.cache =
        Collections.synchronizedMap(
            new LinkedHashMap<>(256, 0.75f, true) {
              @Override
              protected boolean removeEldestEntry(Map.Entry<Key, Frame> e) {
                return size() > JudgingFrames.this.capacity;
              }
            });
    this.hits = counter(meters, "hit");
    this.misses = counter(meters, "miss");
    Gauge.builder("mujuthaek.judging.cache.size", cache, Map::size)
        .tag("cache", "notice")
        .description("판정 캐시에 든 수")
        .register(meters);
  }

  private static Counter counter(MeterRegistry meters, String result) {
    return Counter.builder("mujuthaek.judging.cache")
        .tag("cache", "notice")
        .tag("result", result)
        .description("판정 캐시 조회 (hit = 기억한 판정 틀을 씀)")
        .register(meters);
  }

  /** 공고 여러 개의 판정 틀. 지금 버전 번호만 먼저 묻고, 기억하지 않은 버전만 한 번에 읽어요. 숨김·공개 전·없는 공고는 빠져요. */
  public Map<UUID, Frame> frames(Collection<UUID> ids) {
    Map<UUID, Frame> found = new HashMap<>();
    if (ids.isEmpty()) {
      return found;
    }
    List<UUID> missing = new ArrayList<>();
    notices
        .currentVersions(ids)
        .forEach(
            (id, version) -> {
              Frame cached = cache.get(new Key(id, version));
              if (cached == null) {
                missing.add(id);
              } else {
                found.put(id, cached);
              }
            });
    hits.increment(found.size());
    misses.increment(missing.size());
    if (!missing.isEmpty()) {
      found.putAll(load(missing));
    }
    return found;
  }

  /** 읽어서 기억해요. */
  private Map<UUID, Frame> load(Collection<UUID> ids) {
    Map<UUID, Frame> out = new HashMap<>();
    notices
        .judgingSources(ids)
        .forEach(
            (id, v) -> {
              Frame frame = Frame.of(v.source());
              cache.put(new Key(id, v.version()), frame);
              out.put(id, frame);
            });
    return out;
  }

  /** 뜰 때 열린 공고의 판정 틀을 미리 채워요(뒤에서, 실패해도 서비스는 그대로 떠요). */
  @EventListener(ApplicationReadyEvent.class)
  public void prewarmOnStart() {
    if (!prewarm) {
      return;
    }
    Thread.ofVirtual().name("judging-prewarm").start(this::prewarm);
  }

  void prewarm() {
    long started = System.nanoTime();
    try {
      List<UUID> ids = notices.openNoticeIds(capacity);
      for (int from = 0; from < ids.size(); from += PREWARM_CHUNK) {
        refresh(ids.subList(from, Math.min(from + PREWARM_CHUNK, ids.size())));
      }
      log.info(
          "판정 캐시 미리 채움: 열린 공고 {}개, {}ms", ids.size(), (System.nanoTime() - started) / 1_000_000);
    } catch (RuntimeException e) {
      log.warn("판정 캐시 미리 채우기 실패 (요청 때 채워요)", e);
    }
  }

  /** 공고가 공개·수정되면 그 공고의 새 판정 틀을 미리 채워요 (커밋 뒤). */
  @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT, fallbackExecution = true)
  public void onPublished(NoticePublished e) {
    refreshQuietly(e.noticeId());
  }

  @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT, fallbackExecution = true)
  public void onUpdated(NoticeUpdated e) {
    refreshQuietly(e.noticeId());
  }

  private void refreshQuietly(UUID id) {
    try {
      refresh(List.of(id));
    } catch (RuntimeException ex) {
      log.warn("판정 캐시 채우기 실패 (요청 때 채워요): {}", id, ex);
    }
  }

  /** 지금 버전에 없는 것만 읽어 채워요. 판정 틀을 읽지 못하는 공고는 건너뛰어요(요청 때 다시 해 봐요). */
  void refresh(List<UUID> ids) {
    List<UUID> missing = new ArrayList<>();
    notices
        .currentVersions(ids)
        .forEach(
            (id, version) -> {
              if (!cache.containsKey(new Key(id, version))) {
                missing.add(id);
              }
            });
    if (missing.isEmpty()) {
      return;
    }
    notices
        .judgingSources(missing)
        .forEach(
            (id, v) -> {
              try {
                cache.put(new Key(id, v.version()), Frame.of(v.source()));
              } catch (RuntimeException e) {
                log.warn("판정 틀을 읽지 못해 미리 채우지 않았어요: {}", id, e);
              }
            });
  }

  int size() {
    return cache.size();
  }
}
