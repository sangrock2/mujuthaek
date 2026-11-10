package kr.mujuthaek.api.eligibility.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import kr.mujuthaek.api.eligibility.rule.ApplicantBuilder;
import kr.mujuthaek.api.eligibility.rule.IncomeBenchmarks;
import kr.mujuthaek.api.eligibility.rule.Judge;
import kr.mujuthaek.api.eligibility.rule.Judgment;
import kr.mujuthaek.api.eligibility.rule.Overall;
import kr.mujuthaek.api.notice.NoticeFixtures;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;

/** 소득 구간 대상군 접기 (실측 2026-10-29 구로구 도전숙: 부산 거주 66세 세대원이 소득 구간 대상군으로 지원 가능). */
class IncomeTiersTest {

  private static final String LOW = "월평균소득 50% 이하 및 자산·자동차 기준 충족";
  private static final String MID = "월평균소득 50% 초과 ~100% 이하";

  private static String income(String id, int percent) {
    return """
        {"id":"%s","kind":"INCOME","quote":null,"page":null,"inReview":false,"reviewReason":null,
         "basis":"HOUSEHOLD","standard":"URBAN_WORKER_INCOME","year":2025,"percent":%d}"""
        .formatted(id, percent);
  }

  private static JsonNode frame(String... groups) {
    return NoticeFixtures.JSON.readTree(
        """
        {"referenceDate":"2026-10-20","common":[],"groups":[%s]}"""
            .formatted(String.join(",", groups)));
  }

  private static String group(String id, String name, String... criteria) {
    return """
        {"id":"%s","name":"%s","criteria":[%s]}"""
        .formatted(id, name, String.join(",", criteria));
  }

  private static final String AGE =
      """
      {"id":"age","kind":"AGE","quote":null,"page":null,"inReview":false,"reviewReason":null,"minAge":19,"maxAge":39}""";
  private static final String ASSET =
      """
      {"id":"assets","kind":"ASSET","quote":null,"page":null,"inReview":false,"reviewReason":null,"basis":"HOUSEHOLD","maxWon":245000000}""";

  private static JsonNode dojeon() {
    return frame(
        group("youth", "청년창업인", AGE),
        group("low", LOW, income("income-50", 50), ASSET),
        group("mid", MID, income("income-100", 100)));
  }

  @Test
  void incomeTierGroupsFoldIntoTheTargetAsOneOf() {
    Judgment j = JudgmentReader.read(dojeon());

    assertThat(j.groups()).extracting(Judgment.Group::name).containsExactly("청년창업인");
    var tiers = (Judgment.AnyOf) j.groups().getFirst().criteria().get(1);
    assertThat(tiers.options()).extracting(Judgment.Option::label).containsExactly(LOW, MID);
  }

  @Test
  void a66YearOldWhoOnlyMeetsIncomeIsNotEligible() {
    var a =
        new ApplicantBuilder()
            .birthMonth(1960, 3)
            .region("26110")
            .head(false)
            .household(3)
            .homeOwner(false)
            .income("URBAN_WORKER_INCOME", null, 40)
            .householdIncome("URBAN_WORKER_INCOME", null, 40)
            .incomeYear(2025)
            .assets(100_000_000L)
            .build();

    assertThat(Judge.evaluate(JudgmentReader.read(dojeon()), a).overall())
        .isEqualTo(Overall.INELIGIBLE);
  }

  @Test
  void aYoungApplicantInATierIsStillEligible() {
    var a =
        new ApplicantBuilder()
            .birthMonth(1997, 3)
            .household(1)
            .income("URBAN_WORKER_INCOME", null, 40)
            .householdIncome("URBAN_WORKER_INCOME", null, 40)
            .incomeYear(2025)
            .assets(100_000_000L)
            .build();

    // 2025년 도시근로자 1인 가구 월평균소득 (100%)
    IncomeBenchmarks urban2025 =
        (standard, year, size) ->
            "URBAN_WORKER_INCOME".equals(standard) && year == 2025 && size == 1 ? 3_813_363L : null;
    var result = Judge.evaluate(JudgmentReader.read(dojeon()), a, urban2025);
    assertThat(result.overall()).as(result.toString()).isEqualTo(Overall.ELIGIBLE);
  }

  @Test
  void rankGroupsStayAsTheyAre() {
    // LH처럼 「1순위 …」「2순위」로만 나뉘면(대상 대상군 없음) 그대로 둬요
    JsonNode ranks =
        frame(
            group("r1", "1순위 월평균소득 70% 이하", income("i70", 70)),
            group("r2", "2순위", income("i100", 100)));

    assertThat(JudgmentReader.read(ranks).groups())
        .extracting(Judgment.Group::name)
        .containsExactly("1순위 월평균소득 70% 이하", "2순위");
  }

  @Test
  void aSingleTierBecomesAPlainConditionOfEachTarget() {
    Judgment j =
        JudgmentReader.read(
            frame(
                group("youth", "청년", AGE),
                group("newly", "신혼부부"),
                group("tier", "소득 70% 이하", income("i70", 70))));

    assertThat(j.groups()).extracting(Judgment.Group::name).containsExactly("청년", "신혼부부");
    assertThat(j.groups())
        .allSatisfy(g -> assertThat(g.criteria().getLast()).isInstanceOf(Judgment.Income.class));
  }

  @Test
  void rankOfMatchesExtraction() {
    assertThat(IncomeTiers.rank("1순위")).isEqualTo(1);
    assertThat(IncomeTiers.rank("일반공급 제2순위 장애인")).isEqualTo(2);
    assertThat(IncomeTiers.rank("1·2순위")).isNull();
    assertThat(IncomeTiers.rank("신혼부부")).isNull();
  }
}
