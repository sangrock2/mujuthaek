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
 *
 * <p>연월만 받는 날짜(혼인신고·무주택 시작·통장 가입)는 그 달 말일로 봐서 기간을 가장 짧게 세요. 점수를 실제보다 높게 알려 주지 않으려고요 (2026-11-11:
 * 예전엔 1일로 봐서 통장 2025-05-20 가입이 기준일 2025-11-05에 6개월(2점)로, 실제 5개월(1점)보다 높게 나왔어요). 그 달 1일이면 점수가 더 높아지는
 * 경우는 이유에 「가입일에 따라 N점일 수 있어요」처럼 알려요.
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
    if ("MARRIED".equals(a.marital()) && a.marriedOn() == null) {
      missing.add("applicant.marriedOn");
      return new ScoreItem(key, null, MAX_HOMELESS, "혼인신고 연월을 넣으면 계산돼요");
    }
    // 연월 날짜를 말일로(가장 짧은 기간) 센 점수를 주고, 1일로 세면(가장 긴 기간) 더 높으면 알려요
    LocalDate start = homelessStart(a, true);
    LocalDate longest = homelessStart(a, false);
    if (ref.isBefore(start)) {
      String why =
          start.equals(a.birthDate().plusYears(30)) && !"MARRIED".equals(a.marital())
              ? "만 30세 전 미혼이라 0점이에요"
              : "무주택 기간을 세기 시작하기 전이라 0점이에요";
      return new ScoreItem(key, 0, MAX_HOMELESS, maybeMore(why, 0, homelessPoints(longest, ref)));
    }
    int years = Period.between(start, ref).getYears();
    int points = homelessPoints(start, ref);
    return new ScoreItem(
        key,
        points,
        MAX_HOMELESS,
        maybeMore(years == 0 ? "1년 미만" : years + "년 이상", points, homelessPoints(longest, ref)));
  }

  /** 무주택 기간을 세기 시작하는 날: 만 30세, 그 전에 혼인했으면 혼인신고일, 무주택이 된 날이 더 늦으면 그날. */
  private static LocalDate homelessStart(Input a, boolean endOfMonth) {
    LocalDate thirty = a.birthDate().plusYears(30);
    LocalDate start = thirty;
    if ("MARRIED".equals(a.marital())) {
      LocalDate married = day(a.marriedOn(), endOfMonth);
      if (married.isBefore(thirty)) {
        start = married;
      }
    }
    LocalDate homelessFrom = day(a.homelessSince(), endOfMonth);
    return homelessFrom.isAfter(start) ? homelessFrom : start;
  }

  private static int homelessPoints(LocalDate start, LocalDate ref) {
    if (ref.isBefore(start)) {
      return 0;
    }
    return Math.min(MAX_HOMELESS, 2 + 2 * Period.between(start, ref).getYears());
  }

  private static LocalDate day(YearMonth month, boolean endOfMonth) {
    return endOfMonth ? month.atEndOfMonth() : month.atDay(1);
  }

  /** 그 달 1일로 세면 점수가 더 높을 때 이유에 덧붙여요(연월만 받아 어느 날인지 몰라서). */
  private static String maybeMore(String reason, int points, int best) {
    return best > points ? reason + " · 날짜에 따라 " + best + "점일 수 있어요" : reason;
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
    // 가입 연월을 말일로(가장 짧은 기간) 센 점수를 주고, 1일로 세면 더 높으면 알려요
    int months = Periods.shortestFullMonths(joined, ref);
    int points = subscriptionPoints(months);
    int best = subscriptionPoints(Periods.fullMonths(joined, ref));
    String reason = months < 6 ? "6개월 미만" : months < 12 ? "1년 미만" : (months / 12) + "년 이상";
    return new ScoreItem(key, points, MAX_SUBSCRIPTION, maybeMore(reason, points, best));
  }

  private static int subscriptionPoints(int months) {
    if (months < 6) {
      return 1;
    }
    if (months < 12) {
      return 2;
    }
    return Math.min(MAX_SUBSCRIPTION, 2 + months / 12);
  }
}
