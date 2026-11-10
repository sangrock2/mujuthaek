package kr.mujuthaek.api.eligibility.service;

import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.temporal.ChronoUnit;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.function.Function;
import kr.mujuthaek.api.benefit.service.BenefitForJudgment;
import kr.mujuthaek.api.benefit.service.BenefitQueryService;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.eligibility.dto.response.BenefitEvaluationResponse;
import kr.mujuthaek.api.eligibility.dto.response.BenefitSearchResponse;
import kr.mujuthaek.api.eligibility.rule.Applicant;
import kr.mujuthaek.api.eligibility.rule.IncomeBenchmarks;
import kr.mujuthaek.api.eligibility.rule.benefit.BenefitJudge;
import org.springframework.stereotype.Service;
import tools.jackson.databind.json.JsonMapper;

/**
 * 혜택 판정 (benefit의 조건을 읽어 eligibility 규칙으로). 기준 소득은 요청마다 한 번만 읽어요. 판정 입력은 저장하지 않아요. eligibility →
 * benefit 호출이라 이 모듈에 둬요 (benefit은 다른 모듈을 부르지 않아요).
 */
@Service
public class BenefitEvaluationService {

  private static final ZoneId KOREA = ZoneId.of("Asia/Seoul");

  /** 갚아야 하는 지원 (1년에 받는 돈에 넣지 않아요). */
  private static final Set<String> LOANS = Set.of("DEPOSIT_LOAN", "PURCHASE_LOAN", "LOAN");

  /** 공고의 준비할 돈에 반영할 수 있는 지원. */
  private static final Set<String> PREPARE_COST = Set.of("DEPOSIT_LOAN", "PURCHASE_LOAN");

  private final BenefitQueryService benefits;
  private final CriteriaService criteria;
  private final JsonMapper json;
  private final Clock clock;

  /** 판정 캐시 한 칸: 혜택(지원 내용·조건 포함)과 값을 읽어 둔 조건. */
  private record Compiled(BenefitForJudgment benefit, List<BenefitJudge.Condition> conditions) {}

  private record Key(UUID id, java.time.Instant updatedAt) {}

  /**
   * 열린 혜택의 판정 캐시 (혜택 ID·수정 시각 → 지원 내용·읽어 둔 조건). 맞춤 목록·홈 요약이 요청마다 열린 혜택 수천 개의 조건을 DB에서 읽고 값 JSON을 다시
   * 읽던 것을, 처음 한 번만 해요. 혜택이 바뀌면(새 버전·상태·검수) 수정 시각이 달라져 키가 바뀌므로 옛 값은 쓰지 않아요(오래된 순으로 밀려나요). 공개 데이터만
   * 담아요. 적중률은 {@code mujuthaek_judging_cache_total{cache="benefit"}}.
   */
  private final Map<Key, Compiled> cache;

  private final io.micrometer.core.instrument.Counter hits;
  private final io.micrometer.core.instrument.Counter misses;

  public BenefitEvaluationService(
      BenefitQueryService benefits,
      CriteriaService criteria,
      JsonMapper json,
      Clock clock,
      io.micrometer.core.instrument.MeterRegistry meters,
      @org.springframework.beans.factory.annotation.Value(
              "${mujuthaek.judging.benefit-cache-size:20000}")
          int capacity) {
    this.benefits = benefits;
    this.criteria = criteria;
    this.json = json;
    this.clock = clock;
    this.cache =
        java.util.Collections.synchronizedMap(
            new java.util.LinkedHashMap<>(256, 0.75f, true) {
              @Override
              protected boolean removeEldestEntry(Map.Entry<Key, Compiled> e) {
                return size() > capacity;
              }
            });
    this.hits = counter(meters, "hit");
    this.misses = counter(meters, "miss");
    io.micrometer.core.instrument.Gauge.builder("mujuthaek.judging.cache.size", cache, Map::size)
        .tag("cache", "benefit")
        .description("판정 캐시에 든 수")
        .register(meters);
  }

  private static io.micrometer.core.instrument.Counter counter(
      io.micrometer.core.instrument.MeterRegistry meters, String result) {
    return io.micrometer.core.instrument.Counter.builder("mujuthaek.judging.cache")
        .tag("cache", "benefit")
        .tag("result", result)
        .description("판정 캐시 조회 (hit = 기억한 조건을 씀)")
        .register(meters);
  }

  /** 판정한 혜택 한 건. */
  public record Judged(BenefitForJudgment benefit, BenefitJudge.Result result, long annualWon) {}

  /**
   * 찾아볼 지역의 열린 혜택을 모두 판정해요 (지원 불가 포함). 조건은 캐시(혜택 ID·수정 시각)에서 꺼내 앱에서 판정하고, DB는 캐시에 없는 혜택의 조건만 읽어요.
   */
  public List<Judged> judgeAll(List<String> regionCodes, Applicant applicant) {
    var judge = compiledEvaluator(applicant);
    // 캐시에 같은 수정 시각으로 있는 혜택은 DB가 조건을 읽지 않아요. 그 사이 밀려나도 되게 찾은 것을 이 요청 안에 잡아 둬요
    Map<UUID, Compiled> cached = new java.util.concurrent.ConcurrentHashMap<>();
    var open =
        benefits.openForJudgment(
            regionCodes,
            (id, updatedAt) -> {
              Compiled c = cache.get(new Key(id, updatedAt));
              if (c != null) cached.put(id, c);
              return c != null;
            });
    hits.increment(cached.size());
    return open.stream()
        .map(
            b -> {
              Compiled c = cached.get(b.id());
              if (c == null) {
                misses.increment();
                c = compile(b);
                cache.put(new Key(b.id(), b.updatedAt()), c);
              }
              return judge.apply(c);
            })
        .toList();
  }

  private Compiled compile(BenefitForJudgment b) {
    return new Compiled(b, b.conditions().stream().map(this::condition).toList());
  }

  public BenefitEvaluationResponse evaluate(UUID id, Applicant applicant) {
    BenefitForJudgment b =
        benefits
            .forJudgment(id)
            .orElseThrow(() -> new CustomException(ErrorCode.BENEFIT_NOT_FOUND));
    Judged j = evaluator(applicant).apply(b);
    var r = j.result();
    return new BenefitEvaluationResponse(
        b.id(),
        r.overall(),
        r.reason(),
        r.summary(),
        r.groups().stream()
            .map(g -> new BenefitEvaluationResponse.Group(g.group(), g.status().name(), g.items()))
            .toList(),
        r.notes(),
        j.annualWon());
  }

  /** 요청 하나에서 여러 혜택을 판정할 때 기준 소득을 한 번만 읽어요. */
  Function<BenefitForJudgment, Judged> evaluator(Applicant applicant) {
    var judge = compiledEvaluator(applicant);
    return b -> judge.apply(compile(b));
  }

  private Function<Compiled, Judged> compiledEvaluator(Applicant applicant) {
    IncomeBenchmarks benchmarks = criteria.benchmarks();
    LocalDate today = LocalDate.now(clock.withZone(KOREA));
    return c ->
        new Judged(
            c.benefit(),
            BenefitJudge.judge(
                c.conditions(), c.benefit().needsReview(), applicant, today, benchmarks),
            annualWon(c.benefit()));
  }

  @SuppressWarnings("unchecked")
  private BenefitJudge.Condition condition(BenefitForJudgment.Condition c) {
    Map<String, Object> value =
        c.valueJson() == null ? Map.of() : json.readValue(c.valueJson(), Map.class);
    return new BenefitJudge.Condition(c.type(), value, c.group(), c.known(), c.rawText());
  }

  /**
   * 1년에 받을 수 있는 돈: 금액이 정해진 지원만 (대출 빼고). 월 지원은 최대 12개월.
   *
   * <p>같은 종류의 지원이 여러 줄이면 연차별 금액(1년차·2년차), 유형별 금액(가형·나형), 같은 지원 중복인 경우가 많아서 더하지 않고 가장 큰 것만 넣어요. 다른
   * 종류끼리만 더해요 (2026-10-29 QA: 1~3년차 월 지원을 다 더해 1년 3,600만 원이 되던 것).
   */
  static long annualWon(BenefitForJudgment b) {
    Map<String, Long> byKind = new HashMap<>();
    for (var s : b.supports()) {
      if (s.amountMaxWon() == null || LOANS.contains(s.kind())) continue;
      long won =
          switch (s.amountPer() == null ? "ONCE" : s.amountPer()) {
            case "MONTH" -> s.amountMaxWon() * Math.min(s.months() == null ? 12 : s.months(), 12);
            default -> s.amountMaxWon();
          };
      byKind.merge(s.kind(), won, Math::max);
    }
    return byKind.values().stream().mapToLong(Long::longValue).sum();
  }

  /** 목록 한 줄. */
  BenefitSearchResponse.Item item(Judged j) {
    BenefitForJudgment b = j.benefit();
    LocalDate today = LocalDate.now(clock.withZone(KOREA));
    return new BenefitSearchResponse.Item(
        b.id(),
        b.title(),
        b.agency(),
        b.category(),
        b.summary(),
        b.regionNames(),
        amountText(b),
        j.result().overall() == kr.mujuthaek.api.eligibility.rule.Overall.INELIGIBLE
            ? 0
            : j.annualWon(),
        applyStatus(b, today),
        b.applyEnd(),
        b.applyAlways() || b.applyEnd() == null
            ? null
            : (int) ChronoUnit.DAYS.between(today, b.applyEnd()),
        j.result().overall(),
        b.supports().stream().anyMatch(s -> PREPARE_COST.contains(s.kind())),
        b.needsReview());
  }

  private static String applyStatus(BenefitForJudgment b, LocalDate today) {
    if (b.applyAlways()) return "ALWAYS";
    if (b.applyStart() != null && today.isBefore(b.applyStart())) return "UPCOMING";
    if (b.applyEnd() != null && b.applyEnd().isBefore(today)) return "CLOSED";
    return "APPLYING";
  }

  /** 지원 내용 한 줄 ("월 최대 20만 원 · 12개월", "최대 1억 원 대출", "이자 50% 지원"). 첫 지원 내용 기준이에요. */
  static String amountText(BenefitForJudgment b) {
    if (b.supports().isEmpty()) return null;
    var s = b.supports().getFirst();
    String per =
        switch (s.amountPer() == null ? "" : s.amountPer()) {
          case "MONTH" -> "월 ";
          case "YEAR" -> "연 ";
          default -> "";
        };
    String amount = s.amountMaxWon() == null ? null : per + "최대 " + won(s.amountMaxWon());
    if (amount != null && LOANS.contains(s.kind())) amount += " 대출";
    String months = s.months() == null ? null : s.months() + "개월";
    String rate =
        s.ratePct() == null
            ? null
            : (LOANS.contains(s.kind()) ? "이자 " : "")
                + s.ratePct().stripTrailingZeros().toPlainString()
                + "% 지원";
    String text =
        java.util.stream.Stream.of(amount, months, amount == null ? rate : null)
            .filter(java.util.Objects::nonNull)
            .reduce((x, y) -> x + " · " + y)
            .orElse(null);
    return text != null ? text : s.rawText();
  }

  /** 200000 → "20만 원", 100000000 → "1억 원", 15000000 → "1,500만 원" */
  static String won(long won) {
    long man = won / 10_000;
    if (man == 0) return String.format("%,d원", won);
    long eok = man / 10_000;
    long rest = man % 10_000;
    if (eok == 0) return String.format("%,d만 원", man);
    return rest == 0 ? eok + "억 원" : String.format("%d억 %,d만 원", eok, rest);
  }
}
