package kr.mujuthaek.api.eligibility.rule;

import java.time.LocalDate;
import java.time.Period;
import java.time.YearMonth;
import java.util.ArrayList;
import java.util.List;

/**
 * 청약 가점 (주택공급에 관한 규칙 별표 1의 가점 항목, API 설계 "청약 가점").
 *
 * <ul>
 *   <li>무주택 기간 (최대 32점): 만 30세부터, 그 전에 혼인했으면 혼인신고일부터. 1년 미만 2점, 1년마다 +2점
 *   <li>부양가족 수 (최대 35점): 0명 5점, 1명마다 +5점
 *   <li>청약통장 가입 기간 (최대 17점): 6개월 미만 1점, 1년 미만 2점, 1년마다 +1점
 * </ul>
 *
 * 입력이 빈 항목은 점수 없이(null) 이유와 넣을 칸을 줘요. 총점은 아는 항목의 합이에요.
 */
public final class SubscriptionScore {

  /**
   * 가점 입력. 가점은 연월 단위로 정확해야 계산되는 값이라, 판정 입력(구간 값)과 따로 받아요. 저장하지 않아요.
   *
   * @param homelessSince 무주택 시작 연월 (집이 있으면 null이고 homeOwner = true)
   */
  public record Input(
      LocalDate birthDate,
      String marital,
      YearMonth marriedOn,
      YearMonth homelessSince,
      Boolean homeOwner,
      Integer dependents,
      Subscription subscription) {

    /** 청약통장 가입 연월. */
    public record Subscription(YearMonth joinedOn) {}

    @Override
    public String toString() {
      return kr.mujuthaek.api.common.logging.SensitiveFields.mask(
          "Input[birthDate="
              + birthDate
              + ", marital="
              + marital
              + ", marriedOn="
              + marriedOn
              + ", homelessSince="
              + homelessSince
              + ", homeOwner="
              + homeOwner
              + ", dependents="
              + dependents
              + ", subscription="
              + subscription
              + "]");
    }
  }

  public static final int MAX_HOMELESS = 32;
  public static final int MAX_DEPENDENTS = 35;
  public static final int MAX_SUBSCRIPTION = 17;

  private SubscriptionScore() {}

  /**
   * @param points 모르면 null
   */
  public record ScoreItem(String key, Integer points, int max, String reason) {}

  public record Score(int total, int max, List<ScoreItem> items, List<String> missingInputs) {}

  public static Score calculate(Input a, LocalDate ref) {
    List<String> missing = new ArrayList<>();
    List<ScoreItem> items =
        List.of(homeless(a, ref, missing), dependents(a, missing), subscription(a, ref, missing));
    int total = items.stream().mapToInt(i -> i.points() == null ? 0 : i.points()).sum();
    return new Score(
        total, MAX_HOMELESS + MAX_DEPENDENTS + MAX_SUBSCRIPTION, items, List.copyOf(missing));
  }

  static ScoreItem homeless(Input a, LocalDate ref, List<String> missing) {
    String key = "HOMELESS_PERIOD";
    if (Boolean.TRUE.equals(a.homeOwner())) {
      return new ScoreItem(key, 0, MAX_HOMELESS, "집이 있으면 무주택 기간은 0점이에요");
    }
    if (a.birthDate() == null) {
      missing.add("applicant.birthDate");
      return new ScoreItem(key, null, MAX_HOMELESS, "생년월일을 넣으면 계산돼요");
    }
    if (a.homelessSince() == null) {
      missing.add("applicant.homelessSince");
      return new ScoreItem(key, null, MAX_HOMELESS, "무주택 시작 연월을 넣으면 계산돼요");
    }
    LocalDate thirty = a.birthDate().plusYears(30);
    LocalDate start = thirty;
    if ("MARRIED".equals(a.marital())) {
      if (a.marriedOn() == null) {
        missing.add("applicant.marriedOn");
        return new ScoreItem(key, null, MAX_HOMELESS, "혼인신고 연월을 넣으면 계산돼요");
      }
      LocalDate married = a.marriedOn().atDay(1);
      if (married.isBefore(thirty)) {
        start = married;
      }
    }
    LocalDate homelessFrom = a.homelessSince().atDay(1);
    if (homelessFrom.isAfter(start)) {
      start = homelessFrom;
    }
    if (ref.isBefore(start)) {
      String why =
          start.equals(thirty) && !"MARRIED".equals(a.marital())
              ? "만 30세 전 미혼이라 0점이에요"
              : "무주택 기간을 세기 시작하기 전이라 0점이에요";
      return new ScoreItem(key, 0, MAX_HOMELESS, why);
    }
    int years = Period.between(start, ref).getYears();
    int points = Math.min(MAX_HOMELESS, 2 + 2 * years);
    return new ScoreItem(key, points, MAX_HOMELESS, years == 0 ? "1년 미만" : years + "년 이상");
  }

  static ScoreItem dependents(Input a, List<String> missing) {
    if (a.dependents() == null) {
      missing.add("applicant.dependents");
      return new ScoreItem("DEPENDENTS", null, MAX_DEPENDENTS, "부양가족 수를 넣으면 계산돼요");
    }
    int points = Math.min(MAX_DEPENDENTS, 5 + 5 * a.dependents());
    return new ScoreItem("DEPENDENTS", points, MAX_DEPENDENTS, a.dependents() + "명");
  }

  static ScoreItem subscription(Input a, LocalDate ref, List<String> missing) {
    String key = "SUBSCRIPTION_PERIOD";
    YearMonth joined = a.subscription() == null ? null : a.subscription().joinedOn();
    if (joined == null) {
      missing.add("applicant.subscription.joinedOn");
      return new ScoreItem(key, null, MAX_SUBSCRIPTION, "청약통장 가입 연월을 넣으면 계산돼요");
    }
    int months = Periods.fullMonths(joined, ref);
    if (months < 6) {
      return new ScoreItem(key, 1, MAX_SUBSCRIPTION, "6개월 미만");
    }
    if (months < 12) {
      return new ScoreItem(key, 2, MAX_SUBSCRIPTION, "1년 미만");
    }
    int years = months / 12;
    return new ScoreItem(
        key, Math.min(MAX_SUBSCRIPTION, 2 + years), MAX_SUBSCRIPTION, years + "년 이상");
  }
}
