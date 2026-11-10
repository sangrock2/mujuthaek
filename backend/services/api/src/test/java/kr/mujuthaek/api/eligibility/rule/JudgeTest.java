package kr.mujuthaek.api.eligibility.rule;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.tuple;

import java.time.LocalDate;
import java.util.List;
import kr.mujuthaek.api.eligibility.mapper.JudgmentReader;
import kr.mujuthaek.api.eligibility.mapper.JudgmentReaderTest;
import kr.mujuthaek.api.eligibility.rule.Judgment.Basics;
import org.junit.jupiter.api.Test;

class JudgeTest {

  private static final Basics B = new Basics("x", null, null, false, null);
  private static final LocalDate REF = LocalDate.of(2026, 10, 16);

  /** 청년(만 19~39세)과 신혼부부(혼인 7년 이내) 두 대상, 공통 조건은 무주택. */
  private static Judgment twoGroups() {
    return new Judgment(
        REF,
        List.of(
            new Judgment.Homeless(
                new Basics("homeless", null, null, false, null), "HOUSEHOLD", null)),
        List.of(
            new Judgment.Group(
                "youth",
                "청년",
                List.of(new Judgment.Age(new Basics("age", null, null, false, null), 19, 39))),
            new Judgment.Group(
                "newlywed",
                "신혼부부",
                List.of(
                    new Judgment.Marriage(
                        new Basics("marriage", null, null, false, null), "MARRIED", 7, true)))));
  }

  @Test
  void oneEligibleTargetMakesTheNoticeEligible() {
    var a =
        new ApplicantBuilder().birthMonth(1997, 3).homelessYears("3_5").marital("SINGLE").build();

    var result = Judge.evaluate(twoGroups(), a);

    assertThat(result.overall()).isEqualTo(Overall.ELIGIBLE);
    assertThat(result.targets())
        .extracting(Judge.Target::overall)
        .containsExactly(Overall.ELIGIBLE, Overall.INELIGIBLE);
    assertThat(result.targets().get(0).items())
        .extracting(Item::key)
        .containsExactly("HOMELESS", "AGE");
    assertThat(result.targets().get(0).summary()).isEqualTo(new Judge.Summary(2, 2, 0, 0));
  }

  @Test
  void missingInputsMakeItNeedsInputAndListWhatToFill() {
    var a = new ApplicantBuilder().birthMonth(1997, 3).build();

    var result = Judge.evaluate(twoGroups(), a);

    assertThat(result.overall()).isEqualTo(Overall.NEEDS_INPUT);
    assertThat(result.targets().get(0).overall()).isEqualTo(Overall.NEEDS_INPUT);
    assertThat(result.targets().get(0).summary()).isEqualTo(new Judge.Summary(2, 1, 0, 1));
    assertThat(result.missingInputs())
        .containsExactly("applicant.homelessYears", "applicant.marital");
  }

  @Test
  void ineligibleWhenEveryTargetFails() {
    var a = new ApplicantBuilder().birthMonth(1970, 1).homeOwner(true).marital("SINGLE").build();

    var result = Judge.evaluate(twoGroups(), a);

    assertThat(result.overall()).isEqualTo(Overall.INELIGIBLE);
    assertThat(result.missingInputs()).isEmpty();
  }

  @Test
  void serifulYouthArtistNeedsTheArtistQuestionAnswered() throws Exception {
    // 계약 예시(서리풀 청년주택): 서울 거주·무주택·나이·소득이 맞아도 예술인 증명(ASK)은 직접 확인이라 확인 필요
    Judgment j = JudgmentReader.read(JudgmentReaderTest.example());
    var a =
        new ApplicantBuilder()
            .birthMonth(1997, 3)
            .region("11650")
            .homelessYears("3_5")
            .household(1)
            .income("URBAN_WORKER_INCOME", 30, 40)
            .build();
    // 2025년 도시근로자 1인 월평균소득 (공고 표 50%+가산 = 2,669,354원과 맞는 값)
    IncomeBenchmarks urban2025 =
        (standard, year, size) ->
            "URBAN_WORKER_INCOME".equals(standard) && year == 2025 && size == 1 ? 3_813_363L : null;

    var result = Judge.evaluate(j, a, urban2025);

    var artist = result.targets().get(0);
    assertThat(artist.overall()).isEqualTo(Overall.NEEDS_INPUT);
    assertThat(artist.items())
        .filteredOn(i -> i.status() != Status.MET)
        .extracting(Item::key)
        .containsExactly("ASK");
  }

  private static Basics basics(String id) {
    return new Basics(id, null, null, false, null);
  }

  private static Judgment.Homeless homeless(String id) {
    return new Judgment.Homeless(basics(id), "HOUSEHOLD", null);
  }

  private static Judgment.Income income(String id) {
    return new Judgment.Income(
        basics(id), "HOUSEHOLD", "URBAN_WORKER_INCOME", 2025, 100.0, List.of(), null, List.of());
  }

  private static Judgment.Asset asset(String id) {
    return new Judgment.Asset(basics(id), "HOUSEHOLD", 245_000_000L, List.of());
  }

  private static Judgment.Car car(String id) {
    return new Judgment.Car(basics(id), 45_420_000L, List.of());
  }

  private static Judgment.Ask ask(String id, String question) {
    return new Judgment.Ask(basics(id), question, "YES");
  }

  /** 소득 50% 이하(자산이 1천만 원 이하, 자동차 없음)이고 집이 있는 61세, 인천 남동구, 미혼. */
  private static Applicant richInIncheon() {
    return new ApplicantBuilder()
        .birthMonth(1965, 3)
        .region("28200")
        .household(1)
        .homeOwner(true)
        .marital("SINGLE")
        .income("URBAN_WORKER_INCOME", null, 50)
        .assets(10_000_000L)
        .car(0)
        .build();
  }

  @Test
  void groupMissingTheBaseOthersHaveIsNotEligibleOnItsOwn() {
    // 2026-10-31 운영 「강북구 신혼부부 매입임대」 판정 틀 모양: 「총자산·자동차 기준은 소득 50% 이하인 자에 한함」이 자산·자동차만 가진 대상이 됐어요
    Judgment gangbuk =
        new Judgment(
            REF,
            List.of(),
            List.of(
                new Judgment.Group(
                    "group-1",
                    "(예비)신혼부부",
                    List.of(
                        ask("seoul", "다음 자격을 갖추었나요? 「서울특별시에 거주하는 무주택세대구성원」"),
                        homeless("homeless"),
                        income("income-100"))),
                new Judgment.Group(
                    "group-3", "월평균소득 50% 이하인 신청자", List.of(asset("assets"), car("car")))));

    var result = Judge.evaluate(gangbuk, richInIncheon());

    assertThat(result.overall()).isEqualTo(Overall.NEEDS_INPUT);
    var partial = result.targets().get(1);
    assertThat(partial.overall()).isEqualTo(Overall.NEEDS_INPUT);
    assertThat(partial.items())
        .extracting(Item::key, Item::status)
        .containsExactly(
            tuple("ASSET", Status.MET),
            tuple("CAR_VALUE", Status.MET),
            tuple(Judge.PARTIAL_GROUP, Status.UNKNOWN));
    assertThat(partial.items().get(2).label()).isEqualTo("다른 대상에 있는 무주택·소득 조건이 이 대상에는 없어요");
    assertThat(partial.summary()).isEqualTo(new Judge.Summary(3, 2, 0, 1));
    assertThat(result.targets().get(0).items())
        .extracting(Item::key)
        .doesNotContain(Judge.PARTIAL_GROUP);
    assertThat(result.missingInputs()).as("이 항목은 입력으로 풀리지 않아요").isEmpty();
  }

  @Test
  void baseInCommonConditionsCoversEveryGroup() {
    // 무주택·소득이 공통 조건이면 대상마다 없어도 빠진 게 아니에요 (청년은 나이만으로 지원 가능)
    Judgment shared =
        new Judgment(
            REF,
            List.of(homeless("homeless"), income("income")),
            List.of(
                new Judgment.Group("youth", "청년", List.of(new Judgment.Age(basics("age"), 19, 39))),
                new Judgment.Group(
                    "newlywed",
                    "신혼부부",
                    List.of(
                        new Judgment.Marriage(basics("marriage"), "MARRIED", 7, true),
                        income("income-newlywed")))));
    var a =
        new ApplicantBuilder()
            .birthMonth(1997, 3)
            .homelessYears("3_5")
            .household(1)
            .marital("SINGLE")
            .income("URBAN_WORKER_INCOME", null, 50)
            .householdIncome("URBAN_WORKER_INCOME", null, 50)
            .incomeYear(2025)
            .build();

    var result = Judge.evaluate(shared, a, (standard, year, size) -> 3_813_363L);

    assertThat(result.targets())
        .flatExtracting(Judge.Target::items)
        .extracting(Item::key)
        .doesNotContain(Judge.PARTIAL_GROUP);
    assertThat(result.targets().get(0).overall()).isEqualTo(Overall.ELIGIBLE);
  }

  @Test
  void groupsWithQuestionsOrNoticesWithoutBaseAreLeftAlone() {
    // 질문이 있는 대상은 늘 확인 필요라 건드리지 않고, 무주택·소득이 어디에도 없는 공고는 견줄 기준이 없어요
    Judgment withQuestion =
        new Judgment(
            REF,
            List.of(),
            List.of(
                new Judgment.Group("a", "일반", List.of(homeless("homeless"), income("income"))),
                new Judgment.Group("b", "예비신혼부부", List.of(ask("member", "「예비신혼부부」 대상에 해당하나요?")))));
    Judgment noBase =
        new Judgment(
            REF,
            List.of(),
            List.of(
                new Judgment.Group("youth", "청년", List.of(new Judgment.Age(basics("age"), 19, 39))),
                new Judgment.Group(
                    "newlywed", "신혼부부", List.of(new Judgment.Age(basics("age2"), 19, 39)))));
    var young = new ApplicantBuilder().birthMonth(1997, 3).build();

    assertThat(Judge.evaluate(withQuestion, young).targets())
        .flatExtracting(Judge.Target::items)
        .extracting(Item::key)
        .doesNotContain(Judge.PARTIAL_GROUP);
    var noBaseResult = Judge.evaluate(noBase, young);
    assertThat(noBaseResult.overall()).isEqualTo(Overall.ELIGIBLE);
    assertThat(noBaseResult.targets())
        .flatExtracting(Judge.Target::items)
        .extracting(Item::key)
        .doesNotContain(Judge.PARTIAL_GROUP);
  }

  @Test
  void baseInsideAnyOfCountsAndQuestionsInsideAnyOfDoNot() {
    // 무주택 예외처럼 택일 안에 있는 무주택도 기본 자격이에요. 택일 안의 질문은 다른 선택지로 충족될 수 있어 질문으로 치지 않아요
    Judgment.AnyOf homelessOrException =
        new Judgment.AnyOf(
            basics("homeless-or"),
            List.of(
                new Judgment.Option("기본 기준", List.of(homeless("homeless"))),
                new Judgment.Option("예외", List.of(ask("exception", "다음 예외에 해당하나요?")))));
    Judgment j =
        new Judgment(
            REF,
            List.of(),
            List.of(
                new Judgment.Group("a", "청년", List.of(homelessOrException, income("income"))),
                new Judgment.Group("b", "1순위", List.of(income("income-rank"))),
                new Judgment.Group(
                    "c",
                    "자산 기준",
                    List.of(
                        new Judgment.AnyOf(
                            basics("asset-or"),
                            List.of(
                                new Judgment.Option("기본 기준", List.of(asset("asset"))),
                                new Judgment.Option(
                                    "예외", List.of(ask("asset-exception", "다음 예외에 해당하나요?")))))))));

    var result = Judge.evaluate(j, new ApplicantBuilder().birthMonth(1997, 3).build());

    assertThat(result.targets().get(0).items())
        .extracting(Item::key)
        .doesNotContain(Judge.PARTIAL_GROUP);
    assertThat(result.targets().get(1).items())
        .extracting(Item::label)
        .contains("다른 대상에 있는 무주택 조건이 이 대상에는 없어요");
    assertThat(result.targets().get(2).items())
        .as("택일 안에만 질문이 있으면 질문 없는 대상으로 봐요")
        .extracting(Item::label)
        .contains("다른 대상에 있는 무주택·소득 조건이 이 대상에는 없어요");
  }

  @Test
  void questionInCommonConditionsLeavesEveryGroupAlone() {
    // 공통 조건에 질문이 있으면 어느 대상도 지원 가능이 될 수 없어서 건드리지 않아요
    Judgment j =
        new Judgment(
            REF,
            List.of(ask("savings", "청약통장에 가입했나요?")),
            List.of(
                new Judgment.Group("a", "일반", List.of(homeless("homeless"), income("income"))),
                new Judgment.Group("b", "자산", List.of(asset("assets")))));

    assertThat(Judge.evaluate(j, richInIncheon()).targets())
        .flatExtracting(Judge.Target::items)
        .extracting(Item::key)
        .doesNotContain(Judge.PARTIAL_GROUP);
  }

  @Test
  void groupsSplitBySupplyTypeAreNotCompared() {
    // 추출 시험 test_supply_group_condition_becomes_its_own_group의 모양: 59A형에만 소득 기준이 있고 나머지 주택형은 원문대로
    // 소득 기준이 없어요
    Judgment j =
        new Judgment(
            REF,
            List.of(new Judgment.Age(basics("age"), 19, null)),
            List.of(
                new Judgment.Group("all", Judge.SCOPE_REST, List.of()),
                new Judgment.Group("all-59A", "59A", List.of(income("income-59A")))));

    var result = Judge.evaluate(j, new ApplicantBuilder().birthMonth(1997, 3).build());

    assertThat(result.overall()).isEqualTo(Overall.ELIGIBLE);
    assertThat(result.targets())
        .flatExtracting(Judge.Target::items)
        .extracting(Item::key)
        .doesNotContain(Judge.PARTIAL_GROUP);
  }

  @Test
  void overallRules() {
    assertThat(Overall.best(List.of(Overall.INELIGIBLE, Overall.NEEDS_INPUT)))
        .isEqualTo(Overall.NEEDS_INPUT);
    assertThat(Overall.best(List.of())).isEqualTo(Overall.INELIGIBLE);
    assertThat(Status.any(List.of())).isEqualTo(Status.UNKNOWN);
    assertThat(Status.all(List.of(Status.MET, Status.UNKNOWN))).isEqualTo(Status.UNKNOWN);
  }
}
