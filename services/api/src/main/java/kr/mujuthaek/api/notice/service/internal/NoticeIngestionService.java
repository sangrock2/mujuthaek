package kr.mujuthaek.api.notice.service.internal;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import kr.mujuthaek.api.common.event.NoticeClosed;
import kr.mujuthaek.api.common.event.NoticeLocationsChanged;
import kr.mujuthaek.api.common.event.NoticePublished;
import kr.mujuthaek.api.common.event.NoticeUpdated;
import kr.mujuthaek.api.common.event.PolicyPublished;
import kr.mujuthaek.api.common.event.PolicyUpdated;
import kr.mujuthaek.api.common.id.UuidV7;
import kr.mujuthaek.api.notice.domain.ApplicationStatusCalculator;
import kr.mujuthaek.api.notice.domain.BaseSource;
import kr.mujuthaek.api.notice.domain.CompletedNotice;
import kr.mujuthaek.api.notice.domain.DuplicateRule;
import kr.mujuthaek.api.notice.domain.IngestionOutcome;
import kr.mujuthaek.api.notice.domain.PublicationPolicy;
import kr.mujuthaek.api.notice.domain.PublicationPolicy.Decision;
import kr.mujuthaek.api.notice.domain.ReviewStatus;
import kr.mujuthaek.api.notice.mapper.ExtractionEvent;
import kr.mujuthaek.api.notice.mapper.NoticeContent;
import kr.mujuthaek.api.notice.mapper.NoticeContent.Source;
import kr.mujuthaek.api.notice.repository.ExtractionResultRepository;
import kr.mujuthaek.api.notice.repository.ExtractionResultRepository.WaitingResult;
import kr.mujuthaek.api.notice.repository.FollowUpRepository;
import kr.mujuthaek.api.notice.repository.FollowUpRepository.Attached;
import kr.mujuthaek.api.notice.repository.FollowUpRepository.FollowUpRow;
import kr.mujuthaek.api.notice.repository.NoticeRepository;
import kr.mujuthaek.api.notice.repository.NoticeRepository.CurrentVersion;
import kr.mujuthaek.api.notice.repository.NoticeRepository.Listing;
import kr.mujuthaek.api.notice.repository.NoticeRepository.SourceVersion;
import kr.mujuthaek.api.notice.repository.NoticeRepository.VersionRow;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.JsonNodeFactory;
import tools.jackson.databind.node.ObjectNode;

/**
 * extraction.completed 한 건을 공고로 반영해요. 한 트랜잭션 안에서 수신 기록 → 공개 판단 → 버전 저장 → 이벤트 발행까지 하고, 어느 단계에서 실패해도
 * 모두 되돌려져 같은 메시지를 다시 받으면 처음부터 처리돼요.
 *
 * <ul>
 *   <li>검수 대기·상세 없음은 공개하지 않고 기록만 남겨요. 공개 중인 버전은 그대로예요.
 *   <li>공개 버전은 고치지 않아요. 내용이 바뀐 결과만 새 버전을 만들고, 같은 내용의 승인본은 검수 상태만 승인으로 올려요.
 *   <li>정정 공고: 수집기가 알려 준 원래 공고(supersedesPostId)의 새 버전으로 반영해요. 원래 공고가 아직 공개 전이면 기다렸다가
 *       (PARENT_NOT_PUBLISHED), 원래 공고가 공개될 때 같은 트랜잭션에서 이어서 반영해요. 정정이 반영된 뒤 원래 공고 글이 바뀌어도 정정 내용을
 *       덮어쓰지 않아요.
 *   <li>후속 안내: 원래 공고의 버전을 바꾸지 않고 따로 붙여요(attachFollowUp).
 *   <li>같은 공고: 다른 출처에 올라온 같은 공고는 먼저 공개된 공고에 자동으로 합치고, 내용은 기준 출처 하나만 바꿔요.
 * </ul>
 */
@Service
public class NoticeIngestionService {

  private static final Logger log = LoggerFactory.getLogger(NoticeIngestionService.class);
  private static final Set<String> NOTICE_FIELDS = Set.of("HOUSING", "BUSINESS_SPACE");

  /** 공고가 아니라 판정 틀만 저장하는 정책 분야 (notice.policy_judgments). */
  private static final Set<String> POLICY_FIELDS = Set.of("STARTUP_SUPPORT", "SPACE_RECRUITMENT");

  /** 검수 대기(IN_REVIEW) 정책 판정 틀을 공개하지 않고 수신 기록에만 둔 까닭 (extraction_results.reason). */
  static final String POLICY_IN_REVIEW = "POLICY_IN_REVIEW";

  /** 판정 틀에서 정정으로 보는 부분 (메모·기준일·원본 ID·버전은 빼요). */
  private static final List<String> FRAME_CONDITIONS = List.of("common", "groups", "preferences");

  /** 조건을 비교할 때 빼는 칸: 근거 문장·쪽·확인 필요 까닭 (다시 추출하면 글자만 바뀔 수 있어요). */
  private static final Set<String> FRAME_EVIDENCE = Set.of("quote", "page", "reviewReason");

  /** 후속 안내가 붙거나 바뀌었을 때 NoticeUpdated.changedFields에 넣는 이름. */
  static final String FOLLOW_UPS = "followUps";

  /** 같은 공고의 기준 출처가 아닌 출처의 새 버전. */
  static final String NOT_BASE_SOURCE = "NOT_BASE_SOURCE";

  /** 합치기·되돌리기로 출처가 바뀌었을 때 NoticeUpdated.changedFields에 넣는 이름. */
  static final String SOURCES = "sources";

  /** 새 공고가 같은 공고로 판정돼 기존 공고에 자동으로 합쳐짐. */
  static final String AUTO_MERGED = "AUTO_MERGED";

  /** 내용 해시는 다르지만 비교하는 섹션은 모두 같음 (근거 위치·검증 기록 등만 바뀜). */
  static final String NO_VISIBLE_CHANGE = "NO_VISIBLE_CHANGE";

  private final NoticeRepository notices;
  private final ExtractionResultRepository results;
  private final FollowUpRepository followUps;
  private final NoticeMergeService merges;
  private final PolicyDuplicateService policyDuplicates;
  private final ApplicationEventPublisher events;
  private final JsonMapper json;
  private final Clock clock;

  public NoticeIngestionService(
      NoticeRepository notices,
      ExtractionResultRepository results,
      FollowUpRepository followUps,
      NoticeMergeService merges,
      PolicyDuplicateService policyDuplicates,
      ApplicationEventPublisher events,
      JsonMapper json,
      Clock clock) {
    this.notices = notices;
    this.results = results;
    this.followUps = followUps;
    this.merges = merges;
    this.policyDuplicates = policyDuplicates;
    this.events = events;
    this.json = json;
    this.clock = clock;
  }

  /** 받은 메시지 본문(봉투 JSON)을 반영하고 결과를 돌려줘요. 계약에 맞지 않으면 ExtractionEvent.InvalidEventException. */
  @Transactional
  public IngestionOutcome apply(String messageBody) {
    ExtractionEvent event = ExtractionEvent.from(parse(messageBody));
    results.lock(event.eventId()); // 같은 이벤트가 동시에 오면 앞의 처리가 끝날 때까지 기다려요
    if (results.exists(event.eventId())) {
      return IngestionOutcome.DUPLICATE;
    }
    Instant now = clock.instant();
    Source source = NoticeContent.source(event);
    if (POLICY_FIELDS.contains(event.field())) {
      Decision decision = savePolicy(event, now);
      record(event, source, decision, null, now);
      return decision.outcome();
    }
    if (!NOTICE_FIELDS.contains(event.field())) {
      Decision decision = new Decision(IngestionOutcome.UNSUPPORTED_FIELD, event.field());
      record(event, source, decision, null, now);
      return decision.outcome();
    }
    Applied applied = ingest(event, source, now);
    record(event, source, applied.decision(), applied.noticeId(), now);
    replayWaiting(event, applied, now);
    return applied.decision().outcome();
  }

  /**
   * 정책 판정 틀 저장. 이미 더 높은 버전이 있으면 STALE. 계약 검사가 틀과 지원 지역·원문 주소·상시 여부가 있는지 먼저 봐요.
   *
   * <p>검수 상태별 공개 (사용자 결정 2026-10-23, 상태는 추출이 정해요):
   *
   * <ul>
   *   <li>AUTO_PASSED·PARTIALLY_PASSED: 저장하고 공개해요. PARTIALLY_PASSED 틀의 확인 필요(inReview) 조건은 판정이 확인
   *       필요로 다뤄요.
   *   <li>IN_REVIEW: 틀 전체를 믿을 수 없어요(구간 칸 규칙 틀 등). 저장하지 않아요 — 공개 중인 이전 버전이 있으면 그것을 그대로 두고, 첫 버전이면 승인
   *       전까지 공개하지 않아요. 받은 틀은 수신 기록(extraction_results.payload)에 남고, 검수자가 승인하면 추출이 틀 전체를 APPROVED로
   *       다시 보내 그때 공개본을 바꿔요(따로 대기 칸을 두지 않음).
   *   <li>APPROVED: 공개본을 바꿔요. 같은 버전의 승인본은 승인 아닌 결과로 덮지 않아요(KEPT_APPROVED).
   * </ul>
   */
  private Decision savePolicy(ExtractionEvent event, Instant now) {
    if (!event.reviewStatus().publishable()) {
      Optional<NoticeRepository.PolicyJudgmentState> current =
          notices.policyJudgmentState(event.rawPostId());
      if (current.isPresent() && current.get().version() > event.rawVersion()) {
        return new Decision(IngestionOutcome.STALE, event.field());
      }
      if (current.isPresent()
          && current.get().version() == event.rawVersion()
          && current.get().reviewStatus() == ReviewStatus.APPROVED) {
        return new Decision(IngestionOutcome.KEPT_APPROVED, event.field());
      }
      return new Decision(IngestionOutcome.HELD, POLICY_IN_REVIEW);
    }
    List<String> regions = new java.util.ArrayList<>();
    event.payload().path("regionCodes").forEach(code -> regions.add(code.asString()));
    JsonNode detailUrl = event.payload().path("detailUrl");
    NoticeRepository.PolicyJudgmentRow row =
        new NoticeRepository.PolicyJudgmentRow(
            event.rawPostId(),
            event.field(),
            event.rawVersion(),
            event.eventId(),
            event.title(),
            event.applyStartOn(),
            event.applyEndOn(),
            regions,
            json.writeValueAsString(event.judgment()),
            event.reviewStatus(),
            detailUrl.isString() ? detailUrl.asString() : null,
            event.payload().path("applyAlways").asBoolean(false),
            policyInfoJson(event.payload()));
    // 같은 정책을 동시에 받아도 이전 값 읽기·저장·알림이 엇갈리지 않게 줄 세워요
    notices.lockRawPost(event.rawPostId());
    Optional<NoticeRepository.StoredPolicy> before = notices.storedPolicy(event.rawPostId());
    if (notices.savePolicyJudgment(row, now)) {
      if (before.isEmpty()) {
        // 처음 받은 사업이면 출처에 두 번 올라온 같은 사업인지 견줘 관리자 「중복 의심」에 올려요 (자동으로 지우지 않음)
        policyDuplicates.flag(row.rawPolicyId());
      }
      publishPolicy(before, row, event.reprocess());
      return new Decision(IngestionOutcome.POLICY_JUDGMENT_SAVED, event.field());
    }
    boolean sameVersion =
        notices
            .policyJudgmentState(event.rawPostId())
            .map(current -> current.version() == event.rawVersion())
            .orElse(false);
    return new Decision(
        sameVersion ? IngestionOutcome.KEPT_APPROVED : IngestionOutcome.STALE, event.field());
  }

  /**
   * 처음 저장한 정책이면 PolicyPublished, 더 높은 수집 버전으로 바꿨고 보이는 내용이 달라졌으면 PolicyUpdated를 보내요. 같은 버전을 승인본으로 바꾼
   * 것은 보내지 않아요 (출처 정정이 아니라 검수라서).
   */
  private void publishPolicy(
      Optional<NoticeRepository.StoredPolicy> before,
      NoticeRepository.PolicyJudgmentRow after,
      boolean reprocess) {
    if (before.isEmpty()) {
      events.publishEvent(
          new PolicyPublished(
              after.rawPolicyId(),
              after.field(),
              List.copyOf(after.regionCodes()),
              after.title(),
              reprocess));
      return;
    }
    if (after.rawVersion() <= before.get().version()) {
      return;
    }
    List<String> changed = policyChanges(before.get(), after);
    if (!changed.isEmpty()) {
      events.publishEvent(
          new PolicyUpdated(
              after.rawPolicyId(), after.field(), after.rawVersion(), changed, reprocess));
    }
  }

  /** PolicyUpdated.changedFields: basic · region · schedule · conditions · application (이 순서로). */
  private List<String> policyChanges(
      NoticeRepository.StoredPolicy before, NoticeRepository.PolicyJudgmentRow after) {
    List<String> changed = new java.util.ArrayList<>();
    if (!Objects.equals(before.title(), after.title())) {
      changed.add("basic");
    }
    if (!Set.copyOf(before.regionCodes()).equals(Set.copyOf(after.regionCodes()))) {
      changed.add("region");
    }
    if (!Objects.equals(before.applyStart(), after.applyStart())
        || !Objects.equals(before.applyEnd(), after.applyEnd())
        || before.applyAlways() != after.applyAlways()) {
      changed.add("schedule");
    }
    JsonNode oldFrame = json.readTree(before.frameJson());
    JsonNode newFrame = json.readTree(after.frameJson());
    if (FRAME_CONDITIONS.stream()
        .anyMatch(
            k -> !withoutEvidence(oldFrame.path(k)).equals(withoutEvidence(newFrame.path(k))))) {
      changed.add("conditions");
    }
    if (!Objects.equals(before.detailUrl(), after.detailUrl())
        || !Objects.equals(tree(before.infoJson()), tree(after.infoJson()))) {
      changed.add("application");
    }
    return changed;
  }

  /** 근거 칸(FRAME_EVIDENCE)을 모든 깊이에서 뺀 사본. */
  private static JsonNode withoutEvidence(JsonNode node) {
    if (node.isObject()) {
      ObjectNode copy = JsonNodeFactory.instance.objectNode();
      node.properties()
          .forEach(
              e -> {
                if (!FRAME_EVIDENCE.contains(e.getKey())) {
                  copy.set(e.getKey(), withoutEvidence(e.getValue()));
                }
              });
      return copy;
    }
    if (node.isArray()) {
      ArrayNode copy = JsonNodeFactory.instance.arrayNode();
      node.forEach(item -> copy.add(withoutEvidence(item)));
      return copy;
    }
    return node;
  }

  private JsonNode tree(String jsonText) {
    return jsonText == null ? null : json.readTree(jsonText);
  }

  /**
   * 반영 결과. noticeId는 반영하거나 가리킨 공고 (없으면 null). linked는 이번에 이 글을 공고에 처음 이었는지(새 버전 없이 이은 정정 포함)로, 이 글을
   * 기다리던 정정·후속 안내를 이어서 반영할 때 봐요.
   */
  private record Applied(Decision decision, UUID noticeId, boolean linked) {

    Applied(Decision decision, UUID noticeId) {
      this(decision, noticeId, false);
    }
  }

  private Applied ingest(ExtractionEvent event, Source source, Instant now) {
    if (source.unlinked()) {
      // 연결 없는 정정을 일반 공고로 공개하면 같은 공고가 둘로 보여요. 받은 payload(원래 종류 포함)는 수신 기록에 남아요
      return logged(
          event,
          new Applied(
              new Decision(
                  IngestionOutcome.HELD, ExtractionResultRepository.UNLINKED_RELATED_NOTICE),
              null));
    }
    if (source.followUp()) {
      return logged(event, attachFollowUp(event, source, now));
    }
    if (source.correction()) {
      notices.lockRawPost(source.supersedesPostId()); // 원래 공고 먼저: 원래 공고 처리와 순서가 엇갈리지 않게
    }
    notices.lockRawPost(event.rawPostId());

    Optional<UUID> noticeId = notices.findNoticeIdByPost(event.rawPostId());
    boolean linkedBefore = noticeId.isPresent();
    if (noticeId.isEmpty() && source.correction()) {
      noticeId = notices.findNoticeIdByPost(source.supersedesPostId());
    }
    // 원본 글을 찾은 뒤 그 공고가 합쳐졌으면 합친 공고로 따라가요(합치기와 엇갈렸을 때의 안전장치)
    noticeId = noticeId.map(notices::resolveMerged);
    Optional<CurrentVersion> current = noticeId.flatMap(notices::lockCurrent);
    String contentHash = NoticeContent.hash(event);
    Decision decision =
        PublicationPolicy.decide(
            current.map(c -> published(c, event)).orElse(null),
            new PublicationPolicy.Incoming(
                event.rawVersion(),
                event.reviewStatus(),
                event.notice() != null,
                contentHash,
                source.correction(),
                source.postedOn()));

    if (decision.outcome() == IngestionOutcome.PUBLISHED && source.correction()) {
      // 원래 공고가 아직 공개되지 않음 (검수 대기거나 아직 안 옴): 원래 공고가 공개될 때 이어서 반영해요
      decision =
          new Decision(IngestionOutcome.HELD, ExtractionResultRepository.PARENT_NOT_PUBLISHED);
    } else if (decision.outcome() == IngestionOutcome.PUBLISHED) {
      NewNotice published = publishNew(event, source, contentHash, now);
      noticeId = Optional.of(published.noticeId());
      if (published.mergedInto()) {
        decision = new Decision(IngestionOutcome.PUBLISHED, AUTO_MERGED);
      }
    } else if (decision.outcome() == IngestionOutcome.NEW_VERSION) {
      // 정정 줄기의 최초 원공고 글(정정의 정정 C2 → C1 → N이면 N)
      UUID root =
          notices.rootPostOf(source.correction() ? source.supersedesPostId() : event.rawPostId());
      UUID target = current.orElseThrow().noticeId();
      recordSourceHead(root, target, event, source, now);
      List<String> changed = changedSections(current.orElseThrow(), event);
      Optional<UUID> base = notices.baseRoot(target);
      if (base.isPresent() && !base.get().equals(root)) {
        // 같은 공고의 다른 출처가 기준이에요: 이 출처의 최신 결과만 기억하고 공고 내용은 바꾸지 않아요(출처끼리 번갈아 덮어쓰지 않게)
        decision = new Decision(IngestionOutcome.KEPT_BASE_SOURCE, NOT_BASE_SOURCE);
      } else if (changed.isEmpty()) {
        // 근거 인용 위치·검증 기록·문서 정보·수집 기록처럼 사용자에게 의미 없는 부분만 바뀜: 새 버전과 「바뀐 것 없는 정정」 알림을 만들지 않아요
        decision = new Decision(IngestionOutcome.NO_CHANGE, NO_VISIBLE_CHANGE);
      } else {
        publishVersion(current.orElseThrow(), event, source, contentHash, changed, now);
      }
    } else if (decision.outcome() == IngestionOutcome.APPROVAL_RECORDED) {
      // 내용은 그대로라 새 버전·알림 없이 검수 상태만 올려요. 그래야 같은 원본 버전의 자동 결과가 승인 내용을 덮어쓰지 않아요
      notices.markCurrentApproved(
          current.orElseThrow().noticeId(), event.rawPostId(), event.rawVersion(), now);
    }
    boolean linked = false;
    if (!linkedBefore
        && source.correction()
        && current.isPresent()
        && !decision.publishes() // 새 버전으로 반영했으면 publishVersion이 이미 이었어요
        && decision.outcome() != IngestionOutcome.HELD) {
      // 원래 공고에 속한 정정이면 새 버전을 만들지 않았어도(보이는 변화 없음·내용 같음·기준 출처 아님·더 늦은 정정이 있음 등) 글을 공고에 이어요.
      // 잇지 않으면 이 정정을 다시 정정한 글이 원래 공고를 찾지 못해 PARENT_NOT_PUBLISHED로 계속 기다려요.
      // 검수 대기·상세 없음(HELD)은 공고 내용에 들어가지 않은 글이라 잇지 않아요
      notices.upsertPost(
          event.rawPostId(),
          current.get().noticeId(),
          source.kind(),
          source.supersedesPostId(),
          source.postedOn(),
          now);
      linked = true;
    }
    return logged(event, new Applied(decision, noticeId.orElse(null), linked));
  }

  /** 후속 안내를 원래 공고에 붙여요. 공고 버전은 그대로 두고, 원래 공고가 아직 공개 전이면 기다렸다가 공개될 때 붙여요. */
  private Applied attachFollowUp(ExtractionEvent event, Source source, Instant now) {
    notices.lockRawPost(source.supersedesPostId());
    notices.lockRawPost(event.rawPostId());
    Optional<Attached> attached = followUps.findByRawPost(event.rawPostId());
    Optional<UUID> noticeId =
        attached
            .map(Attached::noticeId)
            .or(() -> notices.findNoticeIdByPost(source.supersedesPostId()));
    String contentHash = NoticeContent.hash(event);
    Decision decision =
        PublicationPolicy.decideFollowUp(
            attached
                .map(
                    a ->
                        new PublicationPolicy.AttachedFollowUp(
                            a.rawVersion(), a.contentHash(), a.reviewStatus()))
                .orElse(null),
            new PublicationPolicy.Incoming(
                event.rawVersion(),
                event.reviewStatus(),
                event.notice() != null,
                contentHash,
                false),
            noticeId.isPresent());
    if (decision.outcome() == IngestionOutcome.FOLLOW_UP_ATTACHED) {
      followUps.upsert(
          new FollowUpRow(
              event.rawPostId(),
              noticeId.orElseThrow(),
              event.rawVersion(),
              event.eventId(),
              source.sourceTitle() != null ? source.sourceTitle() : event.title(),
              source.detailUrl(),
              source.postedOn(),
              json.writeValueAsString(NoticeContent.schedules(event)),
              contentHash,
              event.reviewStatus(),
              // 처음 속한 공고: 원래 공고 글이 처음 속한 공고 (합친 뒤 붙어도 되돌리면 원래 공고로)
              notices.originalNoticeOf(source.supersedesPostId()).orElse(noticeId.orElseThrow())),
          now);
      events.publishEvent(
          new NoticeUpdated(
              noticeId.orElseThrow(),
              notices.fieldOf(noticeId.orElseThrow()).orElse(event.field()),
              List.of(FOLLOW_UPS),
              event.reprocess()));
    } else if (decision.outcome() == IngestionOutcome.APPROVAL_RECORDED) {
      followUps.markApproved(event.rawPostId(), now);
    }
    return new Applied(decision, noticeId.orElse(null));
  }

  private PublicationPolicy.Published published(CurrentVersion current, ExtractionEvent event) {
    Optional<SourceVersion> fromPost = notices.latestFromPost(event.rawPostId());
    // 반영한 정정은 기준 출처의 정정뿐이에요(다른 출처의 정정은 잇기만 함). 그것만 세야 기준 출처의 새 버전이 굳지 않아요
    UUID base = notices.baseRoot(current.noticeId()).orElse(null);
    return new PublicationPolicy.Published(
        fromPost.map(SourceVersion::rawVersion).orElse(null),
        fromPost.map(SourceVersion::reviewStatus).orElse(null),
        current.contentHash(),
        notices.hasCorrection(current.noticeId(), base),
        notices
            .latestOtherCorrectionPostedOn(current.noticeId(), event.rawPostId(), base)
            .orElse(null));
  }

  /**
   * 방금 공개했거나 공고에 처음 이은 글을 기다리던 정정 공고를 이어서 반영해요. 반영한 정정을 기다리던 정정도 차례로 반영돼요. 새 버전 없이 이은 정정(보이는 변화 없음
   * 등)을 기다리던 정정도 여기서 풀려요.
   */
  private void replayWaiting(ExtractionEvent parent, Applied parentApplied, Instant now) {
    if (!parentApplied.decision().publishes() && !parentApplied.linked()) {
      return;
    }
    for (WaitingResult waiting : results.findWaitingFor(parent.rawPostId())) {
      ExtractionEvent correction;
      try {
        correction = ExtractionEvent.fromStored(waiting.eventId(), parse(waiting.payloadJson()));
      } catch (ExtractionEvent.InvalidEventException e) {
        // 저장해 둔 정정이 지금 계약(검사가 강화됨)에 맞지 않음: 이 정정만 보류로 남기고 원래 공고는 그대로 공개해요.
        // 예외를 그대로 두면 원래 공고 메시지까지 실패 큐로 가고, 다시 넣어도 같은 이유로 실패해 원래 공고가 공개되지 않아요
        log.warn(
            "기다리던 정정의 저장본이 계약에 맞지 않아 보류합니다 eventId={} reason={}",
            waiting.eventId(),
            e.getMessage());
        results.updateOutcome(
            waiting.eventId(),
            IngestionOutcome.HELD,
            ExtractionResultRepository.STORED_PAYLOAD_INVALID,
            null);
        continue;
      }
      Applied applied = ingest(correction, NoticeContent.source(correction), now);
      results.updateOutcome(
          waiting.eventId(),
          applied.decision().outcome(),
          applied.decision().reason(),
          applied.noticeId());
      replayWaiting(correction, applied, now);
    }
  }

  /** 새로 공개한 결과. mergedInto면 같은 공고로 판정돼 기존 공고에 합쳤고 noticeId는 그 기존 공고예요. */
  private record NewNotice(UUID noticeId, boolean mergedInto) {}

  private NewNotice publishNew(
      ExtractionEvent event, Source source, String contentHash, Instant now) {
    String publisher = NoticeContent.publisher(event);
    if (publisher != null) {
      // 같은 공고일 수 있는 공개를 줄 세워요: 다른 출처의 같은 공고가 동시에 와도 뒤에 온 쪽이 먼저 공개된 공고를 보고 합쳐져요
      notices.lockIdentity(event.field(), DuplicateRule.publisher(publisher));
    }
    UUID noticeId = UuidV7.next();
    CompletedNotice listValues = CompletedNotice.from(event.payload());
    notices.insertNotice(noticeId, listValues, 1, listing(event, now), now);
    notices.insertVersion(versionRow(noticeId, 1, event, contentHash, List.of()), now);
    notices.upsertPost(
        event.rawPostId(),
        noticeId,
        source.kind(),
        source.supersedesPostId(),
        source.postedOn(),
        now);
    Map<String, Boolean> regions = NoticeContent.regions(event);
    boolean nationwide = NoticeContent.nationwide(event);
    notices.replaceRegions(noticeId, regions, nationwide);
    recordSourceHead(event.rawPostId(), noticeId, event, source, now);
    Optional<UUID> same = mergeIntoSameNotice(noticeId, event, now);
    if (same.isPresent()) {
      // 이미 공개된 같은 공고에 합쳤어요: 새 공고 알림은 보내지 않아요(남은 공고에 NoticeUpdated(sources)가 나가요)
      return new NewNotice(same.get(), true);
    }
    events.publishEvent(
        new NoticePublished(
            noticeId,
            event.field(),
            listValues.regionCode(),
            List.copyOf(regions.keySet()), // 검색 색인과 같은 지역 목록(여러 시도도 모두)
            nationwide,
            event.title(),
            event.reprocess()));
    publishLocations(noticeId, 1, event);
    return new NewNotice(noticeId, false);
  }

  /** area가 위치별 지역 점수를 계산하도록 위치를 알려요. 위치가 없으면 보내지 않아요. */
  private void publishLocations(UUID noticeId, int version, ExtractionEvent event) {
    List<NoticeLocationsChanged.Location> locations = NoticeContent.locations(event);
    if (!locations.isEmpty()) {
      events.publishEvent(new NoticeLocationsChanged(noticeId, version, locations));
    }
  }

  /**
   * 같은 공고로 판정되는 기존 공고가 있으면 새 공고를 그 공고에 자동으로 합쳐요. 다른 출처(기관 게시판·LH API)에 같은 공고가 올라온 경우예요. 먼저 공개된 공고를
   * 남겨 사용자가 보던 공고 ID·버전·알림이 이어지게 하고, 같은 공고가 여럿이면 가장 먼저 공개된 것에 합쳐요. 합칠 수 없으면(분야가 다름 등) 후보로만 남겨요. 합친
   * 뒤 새 공고 원본 글의 정정·새 버전은 남은 공고의 새 버전으로 들어가요.
   */
  private Optional<UUID> mergeIntoSameNotice(UUID noticeId, ExtractionEvent event, Instant now) {
    String publisher = NoticeContent.publisher(event);
    LocalDate announcedOn = NoticeContent.announcedOn(event);
    if (publisher == null || announcedOn == null) {
      return Optional.empty();
    }
    DuplicateRule.Identity incoming =
        new DuplicateRule.Identity(
            publisher,
            announcedOn,
            event.title(),
            Set.copyOf(NoticeContent.sigunguCodes(event)),
            NoticeContent.complexNames(event),
            NoticeContent.supplyType(event));
    for (NoticeRepository.Peer peer :
        notices.findIdentityPeers(
            event.field(), announcedOn, DuplicateRule.WINDOW_DAYS, noticeId)) {
      if (!DuplicateRule.likelySame(incoming, identity(peer))) {
        continue;
      }
      notices.insertDuplicateCandidate(noticeId, peer.noticeId(), DuplicateRule.REASON, now);
      Optional<String> refused = merges.tryMerge(noticeId, peer.noticeId(), event.reprocess());
      if (refused.isEmpty()) {
        log.info("같은 공고라 자동으로 합침 from={} into={}", noticeId, peer.noticeId());
        rebase(peer.noticeId(), false, now, event);
        return Optional.of(peer.noticeId());
      }
      log.warn(
          "같은 공고 후보지만 합치지 못해 후보로 남깁니다 noticeId={} candidateOf={} reason={}",
          noticeId,
          peer.noticeId(),
          refused.get());
    }
    return Optional.empty();
  }

  // ---------- 기준 출처·합치기 ----------

  /** 출처(원래 공고 글)의 마지막 반영 결과를 기록해요. 게시일은 원래 공고 글일 때만 알아요(정정 공고의 게시일은 원래 글 게시일이 아님). */
  private void recordSourceHead(
      UUID root, UUID noticeId, ExtractionEvent event, Source source, Instant now) {
    notices.upsertSourceHead(
        root,
        noticeId,
        event.eventId(),
        NoticeContent.hasPdf(event),
        source.correction() ? null : source.postedOn(),
        now);
  }

  /** 공고의 기준 출처를 다시 골라요(BaseSource 순서). 바뀌었거나 force면 기준 출처의 마지막 결과를 다시 적용해 내용이 다르면 새 버전을 만들어요. */
  private void rebase(UUID noticeId, boolean force, Instant now, ExtractionEvent incoming) {
    List<NoticeRepository.SourceHead> heads = notices.findSourceHeads(noticeId);
    Optional<UUID> currentBase = notices.baseRoot(noticeId);
    Optional<BaseSource.Candidate> best =
        BaseSource.choose(
            heads.stream()
                .map(
                    h ->
                        new BaseSource.Candidate(
                            h.root(), h.hasPdf(), h.postedOn(), h.firstSeenAt()))
                .toList(),
            currentBase.orElse(null));
    if (best.isEmpty()) {
      return;
    }
    UUID root = best.get().root();
    boolean changed = !currentBase.map(root::equals).orElse(false);
    if (changed) {
      notices.setBaseRoot(noticeId, root, now);
      log.info("기준 출처 바꿈 noticeId={} root={}", noticeId, root);
    }
    if (changed || force) {
      heads.stream()
          .filter(h -> h.root().equals(root))
          .findFirst()
          .ifPresent(h -> applyStored(noticeId, h.latestEventId(), now, incoming));
    }
  }

  /** 보관한 결과를 공고의 새 버전으로 다시 적용해요. 내용이 같거나 보이는 섹션이 같으면 아무것도 하지 않아요. */
  private void applyStored(UUID noticeId, UUID eventId, Instant now, ExtractionEvent incoming) {
    ExtractionEvent event;
    if (incoming != null && incoming.eventId().equals(eventId)) {
      event = incoming; // 지금 처리 중인 결과는 아직 수신 기록에 저장 전이에요
    } else {
      Optional<String> payload = notices.storedPayload(eventId);
      if (payload.isEmpty()) {
        return;
      }
      try {
        event = ExtractionEvent.fromStored(eventId, parse(payload.get()));
      } catch (ExtractionEvent.InvalidEventException e) {
        log.warn("보관한 결과가 지금 계약에 맞지 않아 다시 적용하지 않아요 eventId={}", eventId);
        return;
      }
    }
    Optional<CurrentVersion> current = notices.lockCurrent(noticeId);
    if (current.isEmpty()) {
      return;
    }
    String contentHash = NoticeContent.hash(event);
    if (contentHash.equals(current.get().contentHash())) {
      return;
    }
    List<String> changed = changedSections(current.get(), event);
    if (!changed.isEmpty()) {
      publishVersion(current.get(), event, NoticeContent.source(event), contentHash, changed, now);
    }
  }

  /**
   * 이미 공개된 공고끼리 다시 훑어 같은 공고를 합쳐요(자동 합치기 전에 공개됐거나 판별 규칙이 바뀐 경우). 먼저 공개된 공고부터 보고, 나중에 공개된 같은 공고를 먼저
   * 공개된 공고에 합쳐요. 되돌렸거나 같은 공고가 아니라고 표시한 쌍은 건너뛰어요. 합친 수를 돌려줘요.
   */
  @Transactional
  public int mergeDuplicates() {
    Instant now = clock.instant();
    int merged = 0;
    List<NoticeRepository.Peer> open = notices.findOpenIdentities(); // 공개된 순서
    Map<UUID, Integer> order = new HashMap<>();
    for (NoticeRepository.Peer notice : open) {
      order.put(notice.noticeId(), order.size());
    }
    for (NoticeRepository.Peer notice : open) {
      if (notices.mergedInto(notice.noticeId()).isPresent()) {
        continue; // 이번에 이미 다른 공고에 합쳐짐
      }
      DuplicateRule.Identity kept = identity(notice);
      for (NoticeRepository.Peer peer :
          notices.findIdentityPeers(
              notice.field(), notice.announcedOn(), DuplicateRule.WINDOW_DAYS, notice.noticeId())) {
        boolean later = order.getOrDefault(peer.noticeId(), -1) > order.get(notice.noticeId());
        if (!later || !DuplicateRule.likelySame(kept, identity(peer))) {
          continue;
        }
        if (notices.markedNotSame(peer.noticeId(), notice.noticeId())) {
          continue;
        }
        notices.insertDuplicateCandidate(
            peer.noticeId(), notice.noticeId(), DuplicateRule.REASON, now);
        Optional<String> refused = merges.tryMerge(peer.noticeId(), notice.noticeId());
        if (refused.isPresent()) {
          log.warn(
              "같은 공고 후보지만 합치지 못했어요 from={} into={} reason={}",
              peer.noticeId(),
              notice.noticeId(),
              refused.get());
          continue;
        }
        rebase(notice.noticeId(), false, now, null);
        merged++;
        log.info("같은 공고라 합침(다시 훑기) from={} into={}", peer.noticeId(), notice.noticeId());
      }
    }
    return merged;
  }

  private static DuplicateRule.Identity identity(NoticeRepository.Peer notice) {
    return new DuplicateRule.Identity(
        notice.publisher(),
        notice.announcedOn(),
        notice.title(),
        Set.copyOf(notice.sigunguCodes()),
        Set.copyOf(notice.complexNames()),
        notice.supplyType());
  }

  /** 공고를 합쳐요(운영자 명령). 합친 뒤 기준 출처를 다시 골라요. 잘못된 요청이면 IllegalArgumentException. */
  @Transactional
  public void merge(UUID from, UUID into) {
    merges.merge(from, into);
    rebase(into, false, clock.instant(), null);
  }

  /**
   * 합치기를 되돌려요. from 공고를 다시 살리고 처음 속했던 원본 글·후속 안내를 돌려놓은 뒤, 두 공고 모두 기준 출처를 다시 골라 그 출처의 마지막 결과로 내용을
   * 맞춰요. 이미 나간 알림은 되돌릴 수 없어요.
   */
  @Transactional
  public void unmerge(UUID from) {
    UUID into =
        notices
            .mergedInto(from)
            .orElseThrow(() -> new IllegalArgumentException("합쳐진 공고가 아니에요: " + from));
    Instant now = clock.instant();
    notices.lockPostsOf(from, into);
    notices.unmerge(from, into, now);
    notices.markNotSame(from, into, "UNMERGED", now); // 다시 훑기·자동 합치기가 이 쌍을 다시 합치지 않게
    rebase(from, true, now, null);
    rebase(into, true, now, null);
    String field = notices.fieldOf(into).orElseThrow(); // 같은 분야끼리만 합쳐요
    events.publishEvent(new NoticeUpdated(from, field, List.of(SOURCES), false));
    events.publishEvent(new NoticeUpdated(into, field, List.of(SOURCES), false));
    log.info("공고 합치기 되돌림 from={} into={}", from, into);
  }

  /** 지금 공개 버전과 비교해 달라진 섹션 (NoticeUpdated.changedFields). */
  private List<String> changedSections(CurrentVersion current, ExtractionEvent event) {
    return NoticeContent.changedSections(
        parse(current.snapshotJson()),
        parse(current.conditionsJson()),
        parse(current.heldItemsJson()),
        parse(current.applicationWindowsJson()),
        current.judgmentJson() == null ? null : parse(current.judgmentJson()),
        event);
  }

  private void publishVersion(
      CurrentVersion current,
      ExtractionEvent event,
      Source source,
      String contentHash,
      List<String> changed,
      Instant now) {
    int version = current.version() + 1;
    Listing listing = listing(event, now);
    notices.updateNotice(
        current.noticeId(), CompletedNotice.from(event.payload()), version, listing, now);
    notices.insertVersion(
        versionRow(current.noticeId(), version, event, contentHash, changed), now);
    notices.upsertPost(
        event.rawPostId(),
        current.noticeId(),
        source.kind(),
        source.supersedesPostId(),
        source.postedOn(),
        now);
    notices.replaceRegions(
        current.noticeId(), NoticeContent.regions(event), NoticeContent.nationwide(event));
    events.publishEvent(
        new NoticeUpdated(current.noticeId(), event.field(), changed, event.reprocess()));
    if (changed.contains("locations")) {
      publishLocations(current.noticeId(), version, event);
    }
    if (!event.reprocess()
        && ApplicationStatusCalculator.justClosed(current.status(), listing.status())) {
      // 정정으로 접수 기간이 끝난 경우 (예: 마감일 앞당김). 재처리(reprocess)는 상태·이력만 갱신하고 사용자 알림용 이벤트는 보내지 않아요
      LocalDate today = LocalDate.ofInstant(now, ApplicationStatusCalculator.KOREA);
      events.publishEvent(
          new NoticeClosed(
              current.noticeId(),
              event.field(),
              ApplicationStatusCalculator.closedOn(NoticeContent.statusWindows(event), today)));
    }
  }

  /** 버전과 함께 바뀌는 목록 값: 원문 일정으로 계산한 접수 상태와 다시 계산할 시각, 「확인 필요」(보류 항목이 있거나 검수가 필요한 조건이 있음). */
  private static Listing listing(ExtractionEvent event, Instant now) {
    ApplicationStatusCalculator.Result status =
        ApplicationStatusCalculator.calculate(
            NoticeContent.statusWindows(event), NoticeContent.rolling(event), now);
    boolean inReview = false;
    for (JsonNode condition : event.conditions()) {
      inReview |= condition.path("inReview").asBoolean(false);
    }
    return new Listing(
        status.status(),
        status.nextCheckAt(),
        !event.heldItems().isEmpty() || inReview,
        NoticeContent.announcedOn(event));
  }

  private VersionRow versionRow(
      UUID noticeId, int version, ExtractionEvent event, String contentHash, List<String> changed) {
    return new VersionRow(
        noticeId,
        version,
        event.rawPostId(),
        event.rawVersion(),
        event.eventId(),
        event.reviewStatus(),
        json.writeValueAsString(event.payload()),
        json.writeValueAsString(event.conditions()),
        json.writeValueAsString(event.heldItems()),
        json.writeValueAsString(event.applicationWindows()),
        contentHash,
        json.writeValueAsString(changed));
  }

  private void record(
      ExtractionEvent event, Source source, Decision decision, UUID noticeId, Instant now) {
    results.insert(
        event.eventId(),
        event.rawPostId(),
        event.rawVersion(),
        event.reviewStatus(),
        decision.outcome(),
        decision.reason(),
        noticeId,
        source.supersedesPostId(),
        json.writeValueAsString(event.payload()),
        now);
  }

  private static Applied logged(ExtractionEvent event, Applied applied) {
    log.info(
        "추출 결과 반영 eventId={} rawPostId={} rawVersion={} outcome={} reason={} noticeId={}",
        event.eventId(),
        event.rawPostId(),
        event.rawVersion(),
        applied.decision().outcome(),
        applied.decision().reason(),
        applied.noticeId());
    return applied;
  }

  /**
   * 정책 출처 안내(policyInfo)에 마감일 대신 쓰는 신청 기간 안내(applyNote, 「예산 소진 시까지」)를 함께 담아 저장해요. 열린 사업 목록과 화면이
   * 안내에서 읽어요. 둘 다 없으면 null.
   */
  private String policyInfoJson(JsonNode payload) {
    JsonNode info = payload.path("policyInfo");
    JsonNode note = payload.path("applyNote");
    if (!note.isString() || note.asString().isBlank()) {
      return info.isObject() ? json.writeValueAsString(info) : null;
    }
    ObjectNode merged = info.isObject() ? ((ObjectNode) info).deepCopy() : json.createObjectNode();
    merged.put("applyNote", note.asString());
    return json.writeValueAsString(merged);
  }

  private JsonNode parse(String body) {
    try {
      return json.readTree(body);
    } catch (RuntimeException e) {
      throw new ExtractionEvent.InvalidEventException("JSON으로 읽을 수 없어요");
    }
  }
}
