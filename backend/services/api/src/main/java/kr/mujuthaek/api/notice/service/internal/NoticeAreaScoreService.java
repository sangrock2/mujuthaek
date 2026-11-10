package kr.mujuthaek.api.notice.service.internal;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.time.Instant;
import java.util.Set;
import kr.mujuthaek.api.common.event.AreaScoresCalculated;
import kr.mujuthaek.api.notice.mapper.NoticeContent;
import kr.mujuthaek.api.notice.repository.AreaScoreRepository;
import kr.mujuthaek.api.notice.repository.AreaScoreRepository.ScoreRow;
import kr.mujuthaek.api.notice.repository.NoticeRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.json.JsonMapper;

/** area가 계산한 지역 점수 저장. 점수 계산은 area가 하고 notice는 받아서 공고 상세에 보여 줘요. 범위를 벗어난 값은 저장하지 않아요. */
@Service
public class NoticeAreaScoreService {

  private static final Logger log = LoggerFactory.getLogger(NoticeAreaScoreService.class);
  static final Set<String> KINDS = Set.of("LIVING", "COMMERCIAL");

  private final NoticeRepository notices;
  private final AreaScoreRepository scores;
  private final Clock clock;
  private final JsonMapper json;

  public NoticeAreaScoreService(
      NoticeRepository notices, AreaScoreRepository scores, Clock clock, JsonMapper json) {
    this.notices = notices;
    this.scores = scores;
    this.clock = clock;
    this.json = json;
  }

  /** 저장한 점수 개수를 돌려줘요. 없는 공고면 0. */
  @Transactional(propagation = Propagation.REQUIRES_NEW)
  public int save(AreaScoresCalculated event) {
    var current = notices.lockCurrent(event.noticeId());
    if (current.isEmpty()
        || event.noticeVersion() < 1
        || event.noticeVersion() > current.get().version()) {
      log.warn("없는 공고의 지역 점수라 버려요 noticeId={}", event.noticeId());
      return 0;
    }
    var snapshot = json.readTree(current.get().snapshotJson());
    if (event.noticeVersion() != current.get().version()) {
      var original = notices.findLocations(event.noticeId(), event.noticeVersion());
      if (original.isEmpty() || !json.readTree(original.get()).equals(snapshot.path("locations"))) {
        log.info(
            "위치가 바뀐 이전 버전 점수라 버려요 noticeId={} inputVersion={}",
            event.noticeId(),
            event.noticeVersion());
        return 0;
      }
    }
    // 지금 버전에서 보류한 위치(위치 전체나 주소·이름)의 점수는 저장하지 않아요. 상세에서 숨긴 위치예요
    Set<String> locationIds = NoticeContent.locationIds(snapshot);
    Instant now = clock.instant();
    int saved = 0;
    for (AreaScoresCalculated.Score score : event.scores()) {
      if (!valid(score) || !locationIds.contains(score.locationId())) {
        log.warn("지역 점수 값이 올바르지 않아 버려요 noticeId={} {}", event.noticeId(), score);
        continue;
      }
      saved +=
          scores.upsert(
              event.noticeId(),
              event.noticeVersion(),
              new ScoreRow(
                  score.locationId(),
                  score.kind(),
                  BigDecimal.valueOf(score.score()).setScale(2, RoundingMode.HALF_UP),
                  score.calculatedAt(),
                  score.calculationVersion()),
              now);
    }
    return saved;
  }

  static boolean valid(AreaScoresCalculated.Score score) {
    return score != null
        && score.locationId() != null
        && !score.locationId().isBlank()
        && score.kind() != null
        && KINDS.contains(score.kind())
        && Double.isFinite(score.score())
        && score.score() >= 0
        && score.score() <= 100
        && score.calculatedAt() != null
        && score.calculationVersion() != null
        && !score.calculationVersion().isBlank();
  }
}
