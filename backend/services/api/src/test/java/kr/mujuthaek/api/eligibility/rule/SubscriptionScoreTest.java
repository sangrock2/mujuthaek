package kr.mujuthaek.api.eligibility.rule;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class SubscriptionScoreTest {

  private static final LocalDate REF = LocalDate.of(2026, 10, 22);

  @Test
  void fullExample() {
    // 1980년생(만 30세는 2010-03-15), 2015-01부터 무주택 → 11년 → 24점 / 부양가족 2명 → 15점 / 통장 2016-03 → 10년 → 12점
    var a =
        new ScoreInputBuilder()
            .birth(1980, 3, 15)
            .marital("SINGLE")
            .homelessSince(2015, 1)
            .dependents(2)
            .subscription(2016, 3, 100)
            .build();

    var score = SubscriptionScore.calculate(a, REF);

    assertThat(score.items())
        .extracting(SubscriptionScore.ScoreItem::points)
        .containsExactly(24, 15, 12);
    assertThat(score.total()).isEqualTo(51);
    assertThat(score.max()).isEqualTo(84);
    assertThat(score.missingInputs()).isEmpty();
  }

  @ParameterizedTest
  @CsvSource({
    "1997-03-15, SINGLE,  ,        2020-01, 0", // 만 30세 전 미혼
    "1990-01-01, SINGLE,  ,        2015-01, 14", // 무주택은 더 일찍이어도 만 30세(2020-01-01)부터 6년 → 14점
    "1997-03-15, MARRIED, 2022-05, 2022-01, 10", // 30세 전 혼인: 혼인(2022-05)부터 4년 → 10점
    "1960-01-01, SINGLE,  ,        1990-01, 32", // 15년 넘으면 32점
  })
  void homelessPeriod(
      LocalDate birth, String marital, String marriedOn, String since, int expected) {
    var b =
        new ScoreInputBuilder()
            .birth(birth.getYear(), birth.getMonthValue(), birth.getDayOfMonth());
    b.marital(marital);
    if (marriedOn != null) {
      b.married(
          Integer.parseInt(marriedOn.substring(0, 4)), Integer.parseInt(marriedOn.substring(5)));
    }
    b.homelessSince(Integer.parseInt(since.substring(0, 4)), Integer.parseInt(since.substring(5)));
    assertThat(SubscriptionScore.calculate(b.build(), REF).items().get(0).points())
        .isEqualTo(expected);
  }

  @Test
  void reasons() {
    var young =
        new ScoreInputBuilder().birth(1997, 3, 15).marital("SINGLE").homelessSince(2020, 1).build();
    assertThat(SubscriptionScore.calculate(young, REF).items().get(0).reason())
        .isEqualTo("만 30세 전 미혼이라 0점이에요");

    var owner = new ScoreInputBuilder().homeOwner(true).build();
    assertThat(SubscriptionScore.calculate(owner, REF).items().get(0).points()).isZero();
  }

  @Test
  void dependentsAndSubscriptionSteps() {
    assertThat(points(new ScoreInputBuilder().dependents(0), 1)).isEqualTo(5);
    assertThat(points(new ScoreInputBuilder().dependents(6), 1)).isEqualTo(35);
    assertThat(points(new ScoreInputBuilder().dependents(9), 1)).isEqualTo(35);
    assertThat(points(new ScoreInputBuilder().subscription(2026, 6, 1), 2)).isEqualTo(1); // 4개월
    assertThat(points(new ScoreInputBuilder().subscription(2026, 1, 1), 2)).isEqualTo(2); // 9개월
    assertThat(points(new ScoreInputBuilder().subscription(2025, 10, 1), 2)).isEqualTo(3); // 1년
    assertThat(points(new ScoreInputBuilder().subscription(2000, 1, 1), 2)).isEqualTo(17);
  }

  @Test
  void emptyInputsListWhatToFill() {
    var score = SubscriptionScore.calculate(new ScoreInputBuilder().build(), REF);

    assertThat(score.total()).isZero();
    assertThat(score.items()).allSatisfy(i -> assertThat(i.points()).isNull());
    assertThat(score.missingInputs())
        .containsExactly(
            "applicant.birthDate", "applicant.dependents", "applicant.subscription.joinedOn");
  }

  private static Integer points(ScoreInputBuilder b, int index) {
    return SubscriptionScore.calculate(b.build(), REF).items().get(index).points();
  }
}
