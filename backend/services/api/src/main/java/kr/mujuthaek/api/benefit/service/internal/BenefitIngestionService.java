package kr.mujuthaek.api.benefit.service.internal;

import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;
import java.util.Optional;
import kr.mujuthaek.api.benefit.domain.BenefitCategory;
import kr.mujuthaek.api.benefit.domain.BenefitStatus;
import kr.mujuthaek.api.benefit.mapper.PolicyExtractedEvent;
import kr.mujuthaek.api.benefit.repository.BenefitRepository;
import kr.mujuthaek.api.common.event.BenefitPublished;
import kr.mujuthaek.api.common.event.BenefitUpdated;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.json.JsonMapper;

/**
 * policy.extracted를 혜택으로 저장해요 (policy-extracted.draft.md 4장 "저장 규칙"). 처음 받은 정책은 추가, 더 큰 수집 버전과 같은
 * 버전의 검수 결과(quality.reviewed)는 고치고, 그 밖의 같거나 작은 버전은 버려요. 처음 저장했거나 범위 밖이던 정책이 범위 안이 되면
 * BenefitPublished, 범위 안이던 정책의 사용자가 볼 내용이 바뀌면 BenefitUpdated로 알려요 (같은 트랜잭션, notification이 받아요).
 * 재처리는 새 혜택으로 알리지 않고, 바뀜은 reprocess 표시를 달아 알려요. 검수 결과로 처음 보이게 된 혜택은 새 혜택으로 알려요.
 *
 * <p>이번엔 주거 혜택(BENEFIT)만 받아요. 창업지원은 notice.policy_judgments에 있어요.
 */
@Service
public class BenefitIngestionService {

  private static final Logger log = LoggerFactory.getLogger(BenefitIngestionService.class);
  private static final ZoneId KOREA = ZoneId.of("Asia/Seoul");

  private final BenefitRepository benefits;
  private final ApplicationEventPublisher events;
  private final JsonMapper json;
  private final Clock clock;

  public BenefitIngestionService(
      BenefitRepository benefits, ApplicationEventPublisher events, JsonMapper json, Clock clock) {
    this.benefits = benefits;
    this.events = events;
    this.json = json;
    this.clock = clock;
  }

  /** 받은 봉투 글자 그대로. 계약에 맞지 않으면 PolicyExtractedEvent.InvalidEventException. */
  @Transactional
  public void apply(String envelope) {
    PolicyExtractedEvent e = PolicyExtractedEvent.from(json.readTree(envelope));
    if (!"BENEFIT".equals(e.field())) {
      log.info("주거 혜택이 아니라 저장하지 않아요 field={} rawPolicyId={}", e.field(), e.rawPolicyId());
      return;
    }
    var saved = benefits.findByRawPolicyId(e.rawPolicyId());
    // 검수 결과(승인·반려)는 검수 전 결과와 같은 버전으로 와요. 같은 버전을 다 버리면 승인한 수정·반려가 반영되지 않았어요(2026-11-10 코드 검토)
    boolean reviewOfSaved =
        saved.isPresent() && saved.get().version() == e.version() && e.reviewed();
    if (saved.isPresent() && saved.get().version() >= e.version() && !reviewOfSaved) {
      log.info(
          "이미 같거나 새 버전이 있어 버려요 rawPolicyId={} version={} saved={}",
          e.rawPolicyId(),
          e.version(),
          saved.get().version());
      return;
    }
    LocalDate today = LocalDate.now(clock.withZone(KOREA));
    BenefitStatus status =
        BenefitStatus.of(e.relevant(), e.applyAlways(), e.applyStart(), e.applyEnd(), today);
    String category =
        BenefitCategory.of(
                e.supports().stream().map(PolicyExtractedEvent.Support::kind).toList(),
                e.categories())
            .name();
    boolean wasVisible = saved.isPresent() && saved.get().relevant();
    // 바뀐 부분을 고르려고 고치기 전 값을 읽어 둬요 (보이던 혜택만)
    Optional<BenefitRepository.Row> before =
        wasVisible ? benefits.find(saved.get().id()) : Optional.empty();
    var id =
        benefits.save(saved.map(s -> s.id()).orElse(null), e, category, status, clock.instant());
    log.info(
        "혜택 반영 eventId={} rawPolicyId={} version={} benefitId={} status={}",
        e.eventId(),
        e.rawPolicyId(),
        e.version(),
        id,
        status);
    if (!e.relevant()) {
      return; // 범위 밖: 숨김이라 알리지 않아요
    }
    if (!wasVisible) {
      // 검수 결과(승인)로 처음 보이게 된 혜택도 새 혜택이에요. 검수 결과는 알림을 막으려고 reprocess를 달아 오지만 그건 이미 보이던 결과를
      // 확인할 때의 뜻이라, 숨겨져 있다가(범위 밖) 승인으로 처음 보이는 혜택은 새 혜택 알림이 빠졌어요(2026-11-10 재검토. 공고는 검수 승인으로
      // 처음 공개되면 새 공고 알림이 가요). 과거 자료 재처리(검수 결과가 아닌 reprocess)는 그대로 알리지 않아요
      if (!e.reprocess() || e.reviewed()) {
        events.publishEvent(
            new BenefitPublished(
                id, e.field(), e.regionScope(), e.regionCodes(), e.title(), false));
      }
      return;
    }
    List<String> changed = before.map(b -> BenefitChanges.between(b, e, json)).orElse(List.of());
    if (!changed.isEmpty()) {
      events.publishEvent(new BenefitUpdated(id, e.field(), e.version(), changed, e.reprocess()));
    }
  }
}
