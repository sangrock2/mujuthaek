package kr.mujuthaek.api.notice.event;

import kr.mujuthaek.api.common.event.AreaScoresCalculated;
import kr.mujuthaek.api.notice.service.internal.NoticeAreaScoreService;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

/** 위치 작업 완료와 지역 점수 저장을 같은 트랜잭션으로 묶습니다. */
@Component
class AreaScoresListener {

  private final NoticeAreaScoreService scores;

  AreaScoresListener(NoticeAreaScoreService scores) {
    this.scores = scores;
  }

  @EventListener
  void on(AreaScoresCalculated event) {
    scores.save(event);
  }
}
