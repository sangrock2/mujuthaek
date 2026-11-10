package kr.mujuthaek.api.notice.service.internal;

import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.common.event.NoticeUpdated;
import kr.mujuthaek.api.notice.repository.FollowUpRepository;
import kr.mujuthaek.api.notice.repository.NoticeRepository;
import kr.mujuthaek.api.notice.repository.NoticeRepository.DuplicateCandidate;
import kr.mujuthaek.api.notice.repository.NoticeRepository.MergeState;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 같은 공고 합치기. 새 공고가 들어올 때 같은 공고로 판정되면 자동으로 합치고(NoticeIngestionService), 운영자 명령으로도 합치거나 되돌려요.
 *
 * <ul>
 *   <li>합치면 from 공고의 출처(원본 글)·후속 안내가 into 공고로 옮겨가고, from은 목록에서 빠져요. 이후 from의 원본 글에서 오는 결과는 into 공고의
 *       새 버전이 돼요.
 *   <li>from 공고 ID로 조회해도 into 공고가 나와요 (관심 공고·알림 링크가 끊기지 않게).
 *   <li>from의 버전 기록은 지우지 않고 남겨요.
 * </ul>
 */
@Service
public class NoticeMergeService {

  private static final Logger log = LoggerFactory.getLogger(NoticeMergeService.class);
  static final String SOURCES = "sources";

  private final NoticeRepository notices;
  private final FollowUpRepository followUps;
  private final ApplicationEventPublisher events;
  private final Clock clock;

  public NoticeMergeService(
      NoticeRepository notices,
      FollowUpRepository followUps,
      ApplicationEventPublisher events,
      Clock clock) {
    this.notices = notices;
    this.followUps = followUps;
    this.events = events;
    this.clock = clock;
  }

  /** 확인을 기다리는 같은 공고 후보. */
  @Transactional(readOnly = true)
  public List<DuplicateCandidate> pendingCandidates() {
    return notices.findPendingCandidates();
  }

  /** from 공고를 into 공고에 합쳐요. 잘못된 요청이면 IllegalArgumentException (운영자 명령용). */
  @Transactional
  public void merge(UUID from, UUID into) {
    tryMerge(from, into)
        .ifPresent(
            reason -> {
              throw new IllegalArgumentException(reason);
            });
  }

  /**
   * from 공고를 into 공고에 합쳐요. 합칠 수 없으면 바꾸지 않고 이유를 돌려줘요(합쳤으면 빈 값). 자동 합치기·다시 훑기는 이걸 써요: 트랜잭션 안에서 예외가 나면
   * 바깥 트랜잭션이 롤백 대상으로 표시돼, 예외를 잡아도 정상 공고 저장까지 되돌아가요.
   */
  @Transactional
  public Optional<String> tryMerge(UUID from, UUID into) {
    return tryMerge(from, into, false);
  }

  /** reprocess: 과거 공고 재처리 중 합침이면 true (NoticeUpdated에 실어 사용자 알림을 보내지 않게, 리뷰 2026-10-22). */
  @Transactional
  public Optional<String> tryMerge(UUID from, UUID into, boolean reprocess) {
    if (from.equals(into)) {
      return Optional.of("같은 공고는 합칠 수 없어요");
    }
    // 반영과 같은 잠금(원본 글)을 먼저 잡아요. 그러지 않으면 반영이 from 공고를 읽은 뒤 행 잠금에서 기다리다 합치기가 끝나면 공고가 없다고
    // 보고 새 공고로 공개하려다 실패하거나, 정정이 「원래 공고 공개 전」으로 남아 사라져요
    notices.lockPostsOf(from, into);
    // 항상 ID 순서로 잠가 두 합치기가 엇갈려도 교착되지 않게
    Optional<MergeState> lockedFirst = notices.lockForMerge(from.compareTo(into) < 0 ? from : into);
    Optional<MergeState> lockedSecond =
        notices.lockForMerge(from.compareTo(into) < 0 ? into : from);
    if (lockedFirst.isEmpty() || lockedSecond.isEmpty()) {
      return Optional.of("공고가 없어요");
    }
    MergeState first = lockedFirst.get();
    MergeState second = lockedSecond.get();
    MergeState source = first.noticeId().equals(from) ? first : second;
    MergeState target = first.noticeId().equals(into) ? first : second;
    if (source.mergedInto() != null || target.mergedInto() != null) {
      return Optional.of("이미 다른 공고에 합쳐진 공고예요");
    }
    if (!source.field().equals(target.field())) {
      return Optional.of("분야가 다른 공고는 합칠 수 없어요");
    }
    Instant now = clock.instant();
    notices.mergeInto(from, into, now);
    followUps.moveToNotice(from, into, now);
    notices.decideCandidates(from, into, "MERGED", now);
    events.publishEvent(new NoticeUpdated(into, target.field(), List.of(SOURCES), reprocess));
    log.info("공고 합침 from={} into={}", from, into);
    return Optional.empty();
  }

  /** 같은 공고가 아니라고 표시해요. 후보 기록이 없어도 남겨, 다시 훑기·자동 합치기가 이 쌍을 합치지 않게 해요. 대기 중이던 후보가 있었으면 true. */
  @Transactional
  public boolean reject(UUID noticeId, UUID candidateOf) {
    boolean pending =
        !notices.findPendingCandidates().stream()
            .filter(
                c ->
                    (c.noticeId().equals(noticeId) && c.candidateOf().equals(candidateOf))
                        || (c.noticeId().equals(candidateOf) && c.candidateOf().equals(noticeId)))
            .toList()
            .isEmpty();
    notices.markNotSame(noticeId, candidateOf, "REJECTED", clock.instant());
    return pending;
  }
}
