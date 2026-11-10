package kr.mujuthaek.api.notice.service.internal;

import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import kr.mujuthaek.api.common.event.NoticeLocationsChanged;
import kr.mujuthaek.api.common.event.NoticePublished;
import kr.mujuthaek.api.notice.mapper.NoticeContent;
import kr.mujuthaek.api.notice.repository.NoticeRepository;
import kr.mujuthaek.api.notice.repository.NoticeRepository.BackfillRow;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import tools.jackson.databind.json.JsonMapper;

/**
 * 보충 발행. 나중에 붙은 모듈(area·notification)이 그 전에 공개된 공고의 이벤트를 받지 못했을 때, 현재 공개 중인 공고로 이벤트를 다시 보내요.
 *
 * <ul>
 *   <li>NoticePublished는 reprocess=true로 보내 사용자 알림이 한꺼번에 가지 않게 해요.
 *   <li>NoticeLocationsChanged는 현재 버전의 위치로 보내요 (위치가 없는 공고는 건너뛰어요).
 *   <li>묶음(BATCH건)마다 트랜잭션을 따로 열어, 받는 쪽이 커밋 뒤(@TransactionalEventListener)에 받아요.
 * </ul>
 */
@Service
public class NoticeBackfillService {

  private static final Logger log = LoggerFactory.getLogger(NoticeBackfillService.class);
  static final int BATCH = 200;

  /** 다시 보낼 이벤트 종류. */
  public enum Kind {
    PUBLISHED,
    LOCATIONS
  }

  private final NoticeRepository notices;
  private final ApplicationEventPublisher events;
  private final JsonMapper json;
  private final TransactionTemplate transaction;

  public NoticeBackfillService(
      NoticeRepository notices,
      ApplicationEventPublisher events,
      JsonMapper json,
      PlatformTransactionManager transactionManager) {
    this.notices = notices;
    this.events = events;
    this.json = json;
    this.transaction = new TransactionTemplate(transactionManager);
  }

  /** 종류별로 보낸 이벤트 수를 돌려줘요. */
  public Map<Kind, Integer> republish(Set<Kind> kinds, boolean includeClosed) {
    return republish(kinds, includeClosed, BATCH);
  }

  /** 묶음 크기를 정해 보충 발행해요 (테스트에서 작은 묶음으로 확인). */
  public Map<Kind, Integer> republish(Set<Kind> kinds, boolean includeClosed, int batch) {
    Map<Kind, Integer> sent = new EnumMap<>(Kind.class);
    kinds.forEach(kind -> sent.put(kind, 0));
    UUID after = null;
    while (true) {
      UUID cursor = after;
      List<BackfillRow> rows =
          transaction.execute(
              status -> {
                List<BackfillRow> page = notices.findForBackfill(cursor, batch, includeClosed);
                page.forEach(row -> publish(row, kinds, sent));
                return page;
              });
      if (rows == null || rows.isEmpty()) {
        break;
      }
      after = rows.getLast().noticeId();
      if (rows.size() < batch) {
        break;
      }
    }
    log.info("보충 발행 {} (마감 공고 포함: {})", sent, includeClosed);
    return sent;
  }

  private void publish(BackfillRow row, Set<Kind> kinds, Map<Kind, Integer> sent) {
    if (kinds.contains(Kind.PUBLISHED)) {
      // 대표 지역 하나는 공고 반영 때와 같은 규칙(한 시군구 → 그 코드, 한 시도 → xx000, 여러 시도 → null), 목록은 색인 그대로
      events.publishEvent(
          new NoticePublished(
              row.noticeId(),
              row.field(),
              NoticeContent.representativeRegion(row.sigunguCodes()),
              row.sigunguCodes(),
              row.nationwide(),
              row.title(),
              true));
      sent.merge(Kind.PUBLISHED, 1, Integer::sum);
    }
    if (kinds.contains(Kind.LOCATIONS)) {
      List<NoticeLocationsChanged.Location> locations =
          NoticeContent.locations(json.readTree(row.detailJson()));
      if (!locations.isEmpty()) {
        events.publishEvent(new NoticeLocationsChanged(row.noticeId(), row.version(), locations));
        sent.merge(Kind.LOCATIONS, 1, Integer::sum);
      }
    }
  }
}
