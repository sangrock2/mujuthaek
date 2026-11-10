package kr.mujuthaek.api.notification.service.internal;

import java.time.Clock;
import java.time.Duration;
import kr.mujuthaek.api.common.cache.RecentCache;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.notification.client.NotificationServerClient;
import kr.mujuthaek.api.notification.dto.response.AdminNotificationStatsResponse;
import kr.mujuthaek.api.notification.repository.InboxRepository;
import org.springframework.stereotype.Service;

/** 관리자 「알림」 화면: 알림 서버의 발송 결과 + 알림함의 봤는지·눌렀는지. 알림함은 90일만 남아서 90일까지 봐요. */
@Service
public class NotificationStatsService {

  static final int MAX_DAYS = 90;

  /** 같은 기간은 1분 동안 다시 써요. 알림함 기간 전체를 세는 쿼리라 화면을 열 때마다 돌리면 DB가 바빠져요(2026-10-29 부하 시험: 부하 때 0.6초). */
  static final Duration FRESH = Duration.ofMinutes(1);

  private final InboxRepository inbox;
  private final NotificationServerClient server;
  private final Clock clock;
  private final RecentCache<Integer, AdminNotificationStatsResponse> recent;

  public NotificationStatsService(
      InboxRepository inbox, NotificationServerClient server, Clock clock) {
    this.inbox = inbox;
    this.server = server;
    this.clock = clock;
    this.recent = new RecentCache<>(FRESH, clock, this::compute);
  }

  /** 1분 안이면 지난 집계를 써요({@link #FRESH}). */
  public AdminNotificationStatsResponse stats(int days) {
    if (days < 1 || days > MAX_DAYS) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "days는 1~" + MAX_DAYS + "이에요");
    }
    return recent.get(days);
  }

  private AdminNotificationStatsResponse compute(int days) {
    var engagement =
        inbox.engagement(clock.instant().minus(Duration.ofDays(days))).stream()
            .map(
                e ->
                    new AdminNotificationStatsResponse.Engagement(
                        e.type(), e.created(), e.shown(), e.read(), e.clicked()))
            .toList();
    return new AdminNotificationStatsResponse(
        days, server.deliveryStats(days).orElse(null), engagement);
  }
}
