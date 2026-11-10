package kr.mujuthaek.api.eligibility.dto.request;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Past;
import jakarta.validation.constraints.PastOrPresent;
import jakarta.validation.constraints.Pattern;
import java.time.LocalDate;
import java.time.YearMonth;
import kr.mujuthaek.api.common.logging.SensitiveFields;
import kr.mujuthaek.api.eligibility.rule.SubscriptionScore;

/**
 * 청약 가점 입력. 가점은 연월 단위로 계산해야 해서 판정 입력(구간 값)과 따로 정확한 값을 받아요. 모든 칸은 비워도 되고, 값은 저장하지 않아요.
 *
 * @param homelessSince 무주택 시작 연월 (집이 있으면 null + homeOwner = true)
 */
public record ScoreApplicantRequest(
    @Past LocalDate birthDate,
    @Pattern(regexp = "SINGLE|MARRIED|ENGAGED") String marital,
    @PastOrPresent YearMonth marriedOn,
    @PastOrPresent YearMonth homelessSince,
    Boolean homeOwner,
    @Min(0) @Max(20) Integer dependents,
    @Valid SubscriptionRequest subscription) {

  public record SubscriptionRequest(@PastOrPresent YearMonth joinedOn) {}

  public SubscriptionScore.Input toInput() {
    return new SubscriptionScore.Input(
        birthDate,
        marital,
        marriedOn,
        homelessSince,
        homeOwner,
        dependents,
        subscription == null
            ? null
            : new SubscriptionScore.Input.Subscription(subscription.joinedOn()));
  }

  @Override
  public String toString() {
    return SensitiveFields.mask(
        "ScoreApplicantRequest" + toInput().toString().substring("Input".length()));
  }
}
