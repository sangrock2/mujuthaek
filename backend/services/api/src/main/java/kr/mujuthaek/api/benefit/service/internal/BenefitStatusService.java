package kr.mujuthaek.api.benefit.service.internal;

import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;
import kr.mujuthaek.api.benefit.domain.BenefitStatus;
import kr.mujuthaek.api.benefit.repository.BenefitRepository;
import kr.mujuthaek.api.common.event.BenefitClosed;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 날짜가 지나 바뀐 혜택 상태를 다시 저장해요. 새로 마감된 혜택은 BenefitClosed로 알려요. */
@Service
public class BenefitStatusService {

  private static final ZoneId KOREA = ZoneId.of("Asia/Seoul");

  private final BenefitRepository benefits;
  private final ApplicationEventPublisher events;
  private final Clock clock;

  public BenefitStatusService(
      BenefitRepository benefits, ApplicationEventPublisher events, Clock clock) {
    this.benefits = benefits;
    this.events = events;
    this.clock = clock;
  }

  /** 바뀐 혜택 수. */
  @Transactional
  public int refresh() {
    LocalDate today = LocalDate.now(clock.withZone(KOREA));
    int changed = 0;
    for (var row : benefits.visibleStatuses()) {
      BenefitStatus next =
          BenefitStatus.of(true, row.applyAlways(), row.applyStart(), row.applyEnd(), today);
      if (next.name().equals(row.status())) continue;
      benefits.updateStatus(row.id(), next, clock.instant());
      if (next == BenefitStatus.CLOSED) events.publishEvent(new BenefitClosed(row.id(), today));
      changed++;
    }
    return changed;
  }
}
