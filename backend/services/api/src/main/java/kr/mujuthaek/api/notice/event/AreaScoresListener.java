package kr.mujuthaek.api.notice.event;

import kr.mujuthaek.api.common.event.AreaScoresCalculated;
import kr.mujuthaek.api.notice.service.internal.NoticeAreaScoreService;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionalEventListener;

/** area가 보낸 지역 점수를 커밋 뒤에 받아 저장해요. area가 트랜잭션 밖에서 보내도 받아요. */
@Component
class AreaScoresListener {

  private final NoticeAreaScoreService scores;

  AreaScoresListener(NoticeAreaScoreService scores) {
    this.scores = scores;
  }

  @Async
  @TransactionalEventListener(fallbackExecution = true)
  void on(AreaScoresCalculated event) {
    scores.save(event);
  }
}
