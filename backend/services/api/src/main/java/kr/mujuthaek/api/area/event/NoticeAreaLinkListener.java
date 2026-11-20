package kr.mujuthaek.api.area.event;

import kr.mujuthaek.api.area.repository.NoticeLocationJobs;
import kr.mujuthaek.api.area.service.NoticeAreaLinkService;
import kr.mujuthaek.api.common.event.NoticeLocationsChanged;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionalEventListener;

/** 좌표 작업은 공고 공개와 함께 저장하고, 기초 데이터 적재 후 전체 재계산은 비동기로 받습니다. */
@Component
class NoticeAreaLinkListener {

  private final NoticeAreaLinkService link;
  private final NoticeLocationJobs jobs;

  NoticeAreaLinkListener(NoticeAreaLinkService link, NoticeLocationJobs jobs) {
    this.link = link;
    this.jobs = jobs;
  }

  @EventListener
  void on(NoticeLocationsChanged event) {
    jobs.enqueue(event);
  }

  @Async
  @TransactionalEventListener(fallbackExecution = true)
  void on(AreaBaseDataLoaded event) {
    link.onBaseDataLoaded(event.source());
  }
}
