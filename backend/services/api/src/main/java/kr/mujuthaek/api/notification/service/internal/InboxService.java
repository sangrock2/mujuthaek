package kr.mujuthaek.api.notification.service.internal;

import java.time.Clock;
import java.time.Duration;
import java.util.UUID;
import kr.mujuthaek.api.common.dto.response.CursorPageResponse;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.common.pagination.CursorKey;
import kr.mujuthaek.api.common.pagination.CursorQuery;
import kr.mujuthaek.api.notification.dto.response.NotificationItemResponse;
import kr.mujuthaek.api.notification.repository.InboxRepository;
import kr.mujuthaek.api.notification.repository.InboxRepository.Entry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 알림함 읽기·읽음 처리·정리. 줄을 넣는 쪽은 {@link NotificationRequests}예요. */
@Service
public class InboxService {

  private static final Logger log = LoggerFactory.getLogger(InboxService.class);

  /** 커서 정렬 이름 (최근 것부터, ID 순) */
  static final String SORT = "LATEST";

  /** 이만큼 지난 알림은 지워요 (알림 서버 발송 기록과 같은 90일) */
  public static final Duration RETENTION = Duration.ofDays(90);

  static final int PURGE_BATCH = 1_000;

  private final InboxRepository inbox;
  private final Clock clock;

  public InboxService(InboxRepository inbox, Clock clock) {
    this.inbox = inbox;
    this.clock = clock;
  }

  /** 최근 것부터. {@code unreadOnly}면 안 읽은 것만 */
  @Transactional(readOnly = true)
  public CursorPageResponse<NotificationItemResponse> list(
      UUID userId, String cursor, Integer size, boolean unreadOnly) {
    CursorQuery query = CursorQuery.of(cursor, size, SORT);
    UUID before = query.after() == null ? null : query.after().id();
    return CursorPageResponse.from(
        inbox.page(userId, before, unreadOnly, query.fetchSize()),
        query.size(),
        InboxService::item,
        e -> CursorKey.of(SORT, null, e.id()));
  }

  @Transactional(readOnly = true)
  public long unreadCount(UUID userId) {
    return inbox.unreadCount(userId);
  }

  /** 내 알림이 아니면 404예요 (다른 회원 알림이 있는지 알려 주지 않아요) */
  @Transactional
  public void markRead(UUID userId, UUID notificationId) {
    if (!inbox.markRead(userId, notificationId, clock.instant())) {
      throw new CustomException(ErrorCode.NOTIFICATION_NOT_FOUND);
    }
  }

  /** 웹 푸시가 기기에 떴어요 (서비스 워커가 알려 줌). 없는 줄이어도 조용히 넘어가요 */
  @Transactional
  public void markShown(UUID notificationId) {
    inbox.markShown(notificationId, clock.instant());
  }

  /** 푸시나 알림 목록에서 눌렀어요. 없는 줄이어도 조용히 넘어가요 */
  @Transactional
  public void markClicked(UUID notificationId) {
    inbox.markClicked(notificationId, clock.instant());
  }

  @Transactional
  public int markAllRead(UUID userId) {
    return inbox.markAllRead(userId, clock.instant());
  }

  /** 탈퇴한 회원의 알림을 모두 지워요 (회원 삭제와 같은 트랜잭션) */
  @Transactional
  public int deleteAll(UUID userId) {
    int deleted = inbox.deleteAll(userId);
    if (deleted > 0) {
      log.info("탈퇴 회원 알림함 지움: userId={}, 지운 수={}", userId, deleted);
    }
    return deleted;
  }

  /** 90일 지난 알림을 1,000줄씩 지워요. 지운 수를 돌려줘요 */
  public int purgeExpired() {
    var cutoff = clock.instant().minus(RETENTION);
    int total = 0;
    int deleted;
    do {
      deleted = inbox.deleteOlderThan(cutoff, PURGE_BATCH);
      total += deleted;
    } while (deleted == PURGE_BATCH);
    if (total > 0) {
      log.info("90일 지난 알림 지움: {}", total);
    }
    return total;
  }

  private static NotificationItemResponse item(Entry e) {
    return new NotificationItemResponse(
        e.id(),
        e.type(),
        e.targetType() == null
            ? null
            : new NotificationItemResponse.Target(e.targetType(), e.targetId()),
        e.title(),
        e.body(),
        e.linkPath(),
        e.createdAt(),
        e.readAt());
  }
}
