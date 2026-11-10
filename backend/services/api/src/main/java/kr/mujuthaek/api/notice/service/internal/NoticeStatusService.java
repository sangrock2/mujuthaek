package kr.mujuthaek.api.notice.service.internal;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import kr.mujuthaek.api.common.event.NoticeClosed;
import kr.mujuthaek.api.notice.domain.ApplicationStatusCalculator;
import kr.mujuthaek.api.notice.domain.ApplicationStatusCalculator.Result;
import kr.mujuthaek.api.notice.domain.ApplicationStatusCalculator.Window;
import kr.mujuthaek.api.notice.domain.ReviewStatus;
import kr.mujuthaek.api.notice.mapper.NoticeProjection;
import kr.mujuthaek.api.notice.repository.NoticeRepository;
import kr.mujuthaek.api.notice.repository.NoticeRepository.StatusCheckRow;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.json.JsonMapper;

/**
 * 접수 상태 재계산. 다시 계산할 시각이 지난 공고만 골라 상태를 바꾸고, 마감이 아니던 공고가 마감되면 NoticeClosed를 보내요(커밋 뒤 전달). 여러 서버가 동시에
 * 돌아도 같은 공고를 두 번 처리하지 않아요(skip locked).
 */
@Service
public class NoticeStatusService {

  private static final Logger log = LoggerFactory.getLogger(NoticeStatusService.class);

  /** 계산하지 못한 공고의 다음 확인까지 기다리는 시간. */
  static final Duration POSTPONE = Duration.ofDays(1);

  private final NoticeRepository notices;
  private final ApplicationEventPublisher events;
  private final JsonMapper json;
  private final Clock clock;

  public NoticeStatusService(
      NoticeRepository notices, ApplicationEventPublisher events, JsonMapper json, Clock clock) {
    this.notices = notices;
    this.events = events;
    this.json = json;
    this.clock = clock;
  }

  /** 한 묶음(최대 limit건)을 다시 계산하고 처리한 건수를 돌려줘요. 묶음마다 트랜잭션이 따로예요. */
  @Transactional
  public int refreshDue(int limit) {
    Instant now = clock.instant();
    LocalDate today = LocalDate.ofInstant(now, ApplicationStatusCalculator.KOREA);
    List<StatusCheckRow> due = notices.lockDueForStatusCheck(now, limit);
    for (StatusCheckRow row : due) {
      List<Window> windows;
      Result result;
      try {
        var context = json.readTree(row.detailJson());
        boolean approved = row.reviewStatus() == ReviewStatus.APPROVED;
        windows = NoticeProjection.statusWindows(context, approved);
        result =
            ApplicationStatusCalculator.calculate(
                windows, NoticeProjection.rolling(context, approved), now);
      } catch (RuntimeException e) {
        // 한 공고의 일정 자료를 읽지 못해도 묶음 전체를 되돌리지 않아요. 그 공고가 계속 맨 앞에 와서 모든 공고의 마감 처리가
        // 멈추지 않게, 상태는 그대로 두고 다음 확인을 하루 뒤로 미뤄요
        log.warn(
            "접수 상태를 계산하지 못해 하루 뒤로 미룹니다 noticeId={} error={}",
            row.noticeId(),
            e.getClass().getSimpleName());
        notices.updateStatus(row.noticeId(), row.status(), now.plus(POSTPONE), now);
        continue;
      }
      notices.updateStatus(row.noticeId(), result.status(), result.nextCheckAt(), now);
      if (ApplicationStatusCalculator.justClosed(row.status(), result.status())) {
        events.publishEvent(
            new NoticeClosed(
                row.noticeId(), row.field(), ApplicationStatusCalculator.closedOn(windows, today)));
      }
      if (row.status() != result.status()) {
        log.info("접수 상태 변경 noticeId={} {} -> {}", row.noticeId(), row.status(), result.status());
      }
    }
    return due.size();
  }
}
