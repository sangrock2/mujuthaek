package kr.mujuthaek.api.eligibility.service;

import java.time.Clock;
import java.time.LocalDate;
import kr.mujuthaek.api.eligibility.rule.SubscriptionScore;
import org.springframework.stereotype.Service;

/** 청약 가점 계산. 입력은 저장하지 않아요. */
@Service
public class SubscriptionScoreService {

  private final Clock clock;

  public SubscriptionScoreService(Clock clock) {
    this.clock = clock;
  }

  public SubscriptionScore.Score score(SubscriptionScore.Input applicant, LocalDate referenceDate) {
    return SubscriptionScore.calculate(
        applicant, referenceDate == null ? LocalDate.now(clock) : referenceDate);
  }
}
