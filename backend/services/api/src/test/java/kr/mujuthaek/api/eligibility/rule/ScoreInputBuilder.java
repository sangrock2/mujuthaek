package kr.mujuthaek.api.eligibility.rule;

import java.time.LocalDate;
import java.time.YearMonth;

/** 테스트용 청약 가점 입력. 넣지 않은 칸은 비어 있어요(null). */
public final class ScoreInputBuilder {

  private LocalDate birthDate;
  private String marital;
  private YearMonth marriedOn;
  private YearMonth homelessSince;
  private Boolean homeOwner;
  private Integer dependents;
  private SubscriptionScore.Input.Subscription subscription;

  public ScoreInputBuilder birth(int y, int m, int d) {
    birthDate = LocalDate.of(y, m, d);
    return this;
  }

  public ScoreInputBuilder marital(String value) {
    marital = value;
    return this;
  }

  public ScoreInputBuilder married(int y, int m) {
    marital = "MARRIED";
    marriedOn = YearMonth.of(y, m);
    return this;
  }

  public ScoreInputBuilder homelessSince(int y, int m) {
    homelessSince = YearMonth.of(y, m);
    return this;
  }

  public ScoreInputBuilder homeOwner(boolean value) {
    homeOwner = value;
    return this;
  }

  public ScoreInputBuilder dependents(int n) {
    dependents = n;
    return this;
  }

  /** 가입 연월 (납입 횟수는 가점에 쓰지 않아요). */
  public ScoreInputBuilder subscription(int y, int m, int payments) {
    subscription = new SubscriptionScore.Input.Subscription(YearMonth.of(y, m));
    return this;
  }

  public SubscriptionScore.Input build() {
    return new SubscriptionScore.Input(
        birthDate, marital, marriedOn, homelessSince, homeOwner, dependents, subscription);
  }
}
