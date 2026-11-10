package kr.mujuthaek.api.area.event;

import kr.mujuthaek.api.area.service.NoticeAreaLinkService;
import kr.mujuthaek.api.common.event.NoticeLocationsChanged;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * notice의 공고 위치와 area의 기초 데이터 적재를 커밋 뒤에 비동기로 받아요. 좌표 찾기는 외부 API를 불러 느려서 공고 반영을 붙잡지 않게 해요. 트랜잭션 밖에서
 * 보내도 받아요(보충 발행 명령 등).
 *
 * <p>보충 발행(notice.backfill=locations)으로 전체를 다시 돌릴 때는 {@code
 * --spring.task.execution.shutdown.await-termination=true}와 충분한 대기 시간을 같이 줘야 끝까지 처리해요(좌표 찾기는 외부
 * API).
 */
@Component
class NoticeAreaLinkListener {

  private final NoticeAreaLinkService link;

  NoticeAreaLinkListener(NoticeAreaLinkService link) {
    this.link = link;
  }

  @Async
  @TransactionalEventListener(fallbackExecution = true)
  void on(NoticeLocationsChanged event) {
    link.apply(event);
  }

  @Async
  @TransactionalEventListener(fallbackExecution = true)
  void on(AreaBaseDataLoaded event) {
    link.onBaseDataLoaded(event.source());
  }
}
