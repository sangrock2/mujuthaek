package kr.mujuthaek.api.eligibility.service;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.YearMonth;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Consumer;
import kr.mujuthaek.api.benefit.BenefitFixture;
import kr.mujuthaek.api.eligibility.repository.CriteriaStore;
import kr.mujuthaek.api.eligibility.repository.LoanProductStore;
import kr.mujuthaek.api.eligibility.rule.Applicant;
import kr.mujuthaek.api.eligibility.rule.ApplicantBuilder;
import kr.mujuthaek.api.eligibility.rule.Overall;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/**
 * 혜택 맞춤 목록(judgeAll: 판정 칸만 읽고 조건은 캐시에서)이 모든 혜택을 다 읽어 하나씩 판정한 것과 결과가 같은지. 나이 경계·그룹·값 모양을 섞어요.
 * 2026-11-02 나이로 미리 거르던 DB 하위 쿼리를 뺀 뒤에도 같은지 봐요. 오늘은 2026-10-22 고정, 지역은 테스트마다 다른 시군구라 다른 테스트의 혜택과
 * 섞이지 않아요.
 */
class BenefitJudgeAllTest {

  private final BenefitFixture f = new BenefitFixture();
  private final io.micrometer.core.instrument.simple.SimpleMeterRegistry meters =
      new io.micrometer.core.instrument.simple.SimpleMeterRegistry();
  private final CriteriaService criteria =
      new CriteriaService(
          new CriteriaStore(f.jdbc), new LoanProductStore(f.jdbc), BenefitFixture.JSON, f.clock);
  private final BenefitEvaluationService evaluations =
      new BenefitEvaluationService(
          f.queries, criteria, BenefitFixture.JSON, f.clock, meters, 20000);
  private final String region = "4" + (int) (Math.random() * 9000 + 1000);

  @Test
  void prefilteredJudgmentIsTheSameAsJudgingEveryBenefit() {
    seedBenefits();
    List<YearMonth> births =
        List.of(
            YearMonth.of(1997, 3), // 29세
            YearMonth.of(2003, 11), // 22세
            YearMonth.of(1958, 4), // 68세
            YearMonth.of(1986, 10), // 39·40세 경계 (그달 1일생 40, 말일생 39)
            YearMonth.of(1991, 6));
    int ineligible = 0;
    for (YearMonth birth : births) {
      Applicant applicant =
          new ApplicantBuilder().birthMonth(birth.getYear(), birth.getMonthValue()).build();
      Map<UUID, Overall> judged = prefiltered(applicant);
      assertThat(judged).as("출생 %s", birth).isEqualTo(judgedOneByOne(applicant));
      // 목록 한 줄(제목·기관·금액 문구·마감·판정·1년 금액 …)도 전체 칸으로 하나씩 읽어 판정한 것과 같아요
      assertThat(items(applicant)).as("출생 %s 목록 줄", birth).isEqualTo(itemsOneByOne(applicant));
      ineligible += (int) judged.values().stream().filter(o -> o == Overall.INELIGIBLE).count();
    }
    assertThat(ineligible).as("나이로 지원 불가가 나와야 시험이 의미 있어요").isGreaterThan(0);

    // 생년월일이면 경계 달에도 나이가 하나라 그 나이로 판정해요
    for (Applicant applicant :
        List.of(
            new ApplicantBuilder().birthDate(1986, 10, 1).build(),
            new ApplicantBuilder().birthDate(1986, 10, 31).build())) {
      assertThat(prefiltered(applicant))
          .as("생년월일 %s", applicant.birthDate())
          .isEqualTo(judgedOneByOne(applicant));
    }

    // 출생 연월이 없으면 나이는 확인 필요
    Applicant noBirth = new ApplicantBuilder().build();
    assertThat(prefiltered(noBirth)).isEqualTo(judgedOneByOne(noBirth));
  }

  @Test
  void benefitsTooYoungOrOldAreCountedAsIneligibleInTheList() {
    UUID young = benefit(c -> age(c, 1, 19, 39, true));
    UUID old = benefit(c -> age(c, 1, 65, null, true));
    var search = new BenefitSearchService(evaluations);
    var request =
        BenefitFixture.JSON.readValue(
            """
            {"filters":{"regionCodes":["%s"]},"applicant":{"birthMonth":"1997-03"},"size":20}"""
                .formatted(region),
            kr.mujuthaek.api.eligibility.dto.request.BenefitSearchRequest.class);

    var result = search.search(request);

    assertThat(result.summary().ineligible()).isEqualTo(1);
    assertThat(result.items()).extracting(i -> i.id()).containsExactly(young).doesNotContain(old);
  }

  @Test
  void cachedConditionsGiveTheSameJudgmentAndAChangedBenefitIsReadAgain() {
    seedBenefits();
    Applicant applicant = new ApplicantBuilder().birthMonth(1991, 6).build();

    var first = prefiltered(applicant);
    var second = prefiltered(applicant); // 두 번째는 캐시의 조건으로
    assertThat(second).isEqualTo(first).isEqualTo(judgedOneByOne(applicant));
    assertThat(cacheCount("hit")).isPositive();

    // 혜택이 바뀌면(새 버전) 수정 시각이 달라져 새 조건을 읽어요: 35세가 맞던 혜택에 혼인 조건이 붙으면 확인 필요
    UUID raw = UUID.randomUUID();
    f.ingest.apply(
        BenefitFixture.event(raw, 1, p -> withConditions(p, c -> age(c, 1, 19, 39, true))));
    UUID changed = f.queries.findSummaryByRawPolicyId(raw).orElseThrow().benefitId();
    assertThat(prefiltered(applicant).get(changed)).isEqualTo(Overall.ELIGIBLE);
    assertThat(prefiltered(applicant).get(changed)).isEqualTo(Overall.ELIGIBLE); // 캐시
    // 저장할 때 수정 시각이 지금 시각이라, 1분 뒤에 받은 새 버전으로 해요 (시험 시계는 멈춰 있어요)
    var later =
        new kr.mujuthaek.api.benefit.service.internal.BenefitIngestionService(
            f.repository,
            e -> {},
            BenefitFixture.JSON,
            java.time.Clock.offset(f.clock, java.time.Duration.ofMinutes(1)));
    later.apply(
        BenefitFixture.event(
            raw,
            2,
            p ->
                withConditions(
                    p,
                    c -> {
                      age(c, 1, 19, 39, true);
                      other(c, 2, "MARITAL", "{\"in\": [\"MARRIED\"]}");
                    })));
    assertThat(prefiltered(applicant).get(changed)).isEqualTo(Overall.NEEDS_INPUT);
    assertThat(prefiltered(applicant)).isEqualTo(judgedOneByOne(applicant));
  }

  private void withConditions(ObjectNode p, Consumer<ArrayNode> conditions) {
    var source = p.withObject("source");
    source.put("regionScope", "SIGUNGU");
    source.putArray("regionCodes").add(region);
    conditions.accept(p.putArray("conditions"));
  }

  private double cacheCount(String result) {
    return meters
        .get("mujuthaek.judging.cache")
        .tag("cache", "benefit")
        .tag("result", result)
        .counter()
        .count();
  }

  private Map<UUID, Overall> prefiltered(Applicant applicant) {
    Map<UUID, Overall> out = new LinkedHashMap<>();
    evaluations
        .judgeAll(List.of(region), applicant)
        .forEach(j -> out.put(j.benefit().id(), j.result().overall()));
    return out;
  }

  /** 예전처럼 모든 혜택의 조건을 읽어 하나씩 판정 */
  private Map<UUID, Overall> judgedOneByOne(Applicant applicant) {
    var judge = evaluations.evaluator(applicant);
    Map<UUID, Overall> out = new LinkedHashMap<>();
    f.queries.openForJudgment(List.of(region)).stream()
        .map(judge)
        .forEach(j -> out.put(j.benefit().id(), j.result().overall()));
    return out;
  }

  private List<kr.mujuthaek.api.eligibility.dto.response.BenefitSearchResponse.Item> items(
      Applicant applicant) {
    return evaluations.judgeAll(List.of(region), applicant).stream()
        .map(evaluations::item)
        .sorted(java.util.Comparator.comparing(i -> i.id().toString()))
        .toList();
  }

  /** 혜택마다 전체 칸(상세와 같은 select *)으로 다시 읽어 하나씩 판정한 목록 줄 */
  private List<kr.mujuthaek.api.eligibility.dto.response.BenefitSearchResponse.Item> itemsOneByOne(
      Applicant applicant) {
    var judge = evaluations.evaluator(applicant);
    return f.queries.openForJudgment(List.of(region)).stream()
        .map(b -> f.queries.forJudgment(b.id()).orElseThrow())
        .map(judge)
        .map(evaluations::item)
        .sorted(java.util.Comparator.comparing(i -> i.id().toString()))
        .toList();
  }

  private void seedBenefits() {
    benefit(c -> age(c, 1, 19, 39, true)); // 청년
    benefit(c -> age(c, 1, 40, 60, true)); // 중장년
    benefit(c -> age(c, 1, 65, null, true)); // 노인 (min만)
    benefit(c -> age(c, 1, null, 34, true)); // max만
    benefit(c -> age(c, 1, 19, 39, false)); // 값을 모르는 나이 → 확인 필요
    benefit(c -> ageRaw(c, 1, "{\"min\": 19.0, \"max\": 39.9}")); // 소수는 정수로 버려요
    benefit(c -> ageRaw(c, 1, "{\"min\": \"19\", \"max\": \"24\"}")); // 문자는 값이 없는 것
    benefit(c -> ageRaw(c, 1, "{}"));
    benefit(
        c -> { // 같은 그룹의 다른 조건과 「또는」
          age(c, 1, 40, 60, true);
          other(c, 1, "MARITAL", "{\"in\": [\"SINGLE\"]}");
        });
    benefit(
        c -> { // 같은 그룹의 나이 둘 (19~24 또는 30~35)
          age(c, 1, 19, 24, true);
          age(c, 1, 30, 35, true);
        });
    benefit(
        c -> { // 다른 그룹(그리고)과 함께
          other(c, 1, "MARITAL", "{\"in\": [\"SINGLE\"]}");
          age(c, 2, 40, 60, true);
        });
    benefit(
        c -> { // 안내 조건은 판정에서 빠져요
          other(c, 1, "EXCLUSIVE", null);
          age(c, 1, 40, 60, true);
        });
    benefit(c -> other(c, 1, "EXCLUSIVE", null)); // 안내 조건만
    benefit(c -> {}); // 조건 없음
    benefit(
        c -> age(c, 1, 40, 60, true),
        p -> p.withObject("quality").put("needsReview", true)); // 검수 중이어도 지원 불가는 지원 불가
  }

  private UUID benefit(Consumer<ArrayNode> conditions) {
    return benefit(conditions, p -> {});
  }

  private UUID benefit(Consumer<ArrayNode> conditions, Consumer<ObjectNode> more) {
    return f.benefit(
        p -> {
          var source = p.withObject("source");
          source.put("regionScope", "SIGUNGU");
          source.putArray("regionCodes").add(region);
          conditions.accept(p.putArray("conditions"));
          more.accept(p);
        });
  }

  private static void age(ArrayNode c, int group, Integer min, Integer max, boolean known) {
    ObjectNode value = BenefitFixture.JSON.createObjectNode();
    if (min != null) value.put("min", min);
    if (max != null) value.put("max", max);
    line(c, group, "AGE", known ? value : null, known);
  }

  private static void ageRaw(ArrayNode c, int group, String value) {
    line(c, group, "AGE", (ObjectNode) BenefitFixture.JSON.readTree(value), true);
  }

  private static void other(ArrayNode c, int group, String type, String value) {
    line(
        c,
        group,
        type,
        value == null ? null : (ObjectNode) BenefitFixture.JSON.readTree(value),
        value != null);
  }

  private static void line(ArrayNode c, int group, String type, ObjectNode value, boolean known) {
    ObjectNode line =
        c.addObject()
            .put("type", type)
            .put("group", group)
            .put("known", known)
            .put("origin", "RULE")
            .put("rawText", type + " " + group)
            .put("evidence", type)
            .put("confidence", 1);
    if (value == null) line.putNull("value");
    else line.set("value", value);
  }
}
