package kr.mujuthaek.api.eligibility;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.net.URISyntaxException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;
import kr.mujuthaek.api.eligibility.dto.request.JudgmentApplicantRequest;
import kr.mujuthaek.api.eligibility.mapper.ApplicantMapper;
import kr.mujuthaek.api.eligibility.mapper.FrameReader;
import kr.mujuthaek.api.eligibility.mapper.FrameSpec;
import kr.mujuthaek.api.eligibility.rule.frame.Answer;
import kr.mujuthaek.api.eligibility.rule.frame.Evaluation;
import kr.mujuthaek.api.eligibility.rule.frame.Frame;
import kr.mujuthaek.api.eligibility.rule.frame.FrameJudge;
import kr.mujuthaek.api.eligibility.rule.frame.FrameJudgment;
import kr.mujuthaek.api.eligibility.rule.frame.Input;
import org.junit.jupiter.api.DynamicContainer;
import org.junit.jupiter.api.DynamicNode;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.TestFactory;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * 정답 케이스: 판정 틀(정의서 예시를 그대로 쓴 것)에 사용자 입력을 넣고, 적어 둔 기대 결과와 같은지 봐요. 스프링 없이 돌아요.
 *
 * <p>파일: src/test/resources/eligibility/frames/{housing,business-space,startup-support}/*.json. 파일
 * 하나 = 틀 하나 + 케이스 여러 개. 틀은 모두 공식 JSON Schema를 통과했고, 사업공간·창업지원 기대값은 정의서의 참조 판정과도 같아요.
 *
 * <p>기대값 칸: result, rank(내 순위), groups(대상군 ID → 판정), criteria(조건 ID → 판정, ANY_OF 안쪽 포함),
 * preferences, summaries(기준 설명), reasons, missingInputs(공고 결과의 부족한 입력), criterionMissing(조건 하나의 부족한
 * 입력), questions(질문 ID → 받은 답).
 */
class FrameCasesTest {

  private static final JsonMapper JSON = JsonMapper.builder().build();
  private static final FrameJudge JUDGE =
      new FrameJudge(MigrationBaseValues.load(), MigrationDeposits.load());
  private static final Map<String, FrameSpec> SPECS =
      Map.of(
          "housing", FrameSpec.HOUSING,
          "business-space", FrameSpec.BUSINESS_SPACE,
          "startup-support", FrameSpec.STARTUP_SUPPORT);

  @TestFactory
  Stream<DynamicNode> housing() {
    return cases("housing");
  }

  @TestFactory
  Stream<DynamicNode> businessSpace() {
    return cases("business-space");
  }

  @TestFactory
  Stream<DynamicNode> startupSupport() {
    return cases("startup-support");
  }

  @TestFactory
  Stream<DynamicTest> everyFieldHasAtLeastTenCases() {
    return SPECS.keySet().stream()
        .map(
            field ->
                DynamicTest.dynamicTest(
                    field,
                    () -> {
                      int count = 0;
                      for (Path file : files(field)) {
                        count += JSON.readTree(file.toFile()).get("cases").size();
                      }
                      assertThat(count).as("완료 기준: 정답 케이스 10개").isGreaterThanOrEqualTo(10);
                    }));
  }

  private static Stream<DynamicNode> cases(String field) {
    List<DynamicNode> containers = new ArrayList<>();
    for (Path file : files(field)) {
      JsonNode root = JSON.readTree(file.toFile());
      Frame frame = FrameReader.read(root.get("frame"), SPECS.get(field));
      // 틀에 기준일이 없으면(창업지원) 파일의 judgedOn(판정하는 날)으로 계산해요
      LocalDate judgedOn =
          root.has("judgedOn")
              ? LocalDate.parse(root.get("judgedOn").stringValue())
              : frame.referenceDate();
      List<DynamicTest> tests = new ArrayList<>();
      for (JsonNode c : root.get("cases")) {
        tests.add(
            DynamicTest.dynamicTest(
                c.get("name").stringValue(), () -> check(frame, c, c.get("expect"), judgedOn)));
      }
      containers.add(
          DynamicContainer.dynamicContainer(root.get("description").stringValue(), tests));
    }
    return containers.stream();
  }

  private static void check(Frame frame, JsonNode c, JsonNode expect, LocalDate judgedOn) {
    JudgmentApplicantRequest request =
        JSON.treeToValue(c.get("applicant"), JudgmentApplicantRequest.class);
    Map<String, Answer> answers =
        c.has("answers")
            ? JSON.convertValue(c.get("answers"), new TypeReference<Map<String, Answer>>() {})
            : Map.of();
    FrameJudgment judgment =
        JUDGE.judge(frame, ApplicantMapper.toApplicant(request, answers), judgedOn);
    Map<String, Evaluation> byId = new HashMap<>();
    judgment.common().forEach(e -> index(e, byId));
    judgment.groups().forEach(g -> g.criteria().forEach(e -> index(e, byId)));
    judgment.preferences().forEach(p -> p.criteria().forEach(e -> index(e, byId)));

    if (expect.has("result")) {
      assertThat(judgment.result().name())
          .as("공고 결과")
          .isEqualTo(expect.get("result").stringValue());
    }
    if (expect.has("rank")) {
      assertThat(judgment.rank())
          .as("내 순위")
          .isEqualTo(expect.get("rank").isNull() ? null : expect.get("rank").intValue());
    }
    expect
        .path("groups")
        .properties()
        .forEach(
            e ->
                assertThat(
                        judgment.groups().stream()
                            .filter(g -> g.group().id().equals(e.getKey()))
                            .findFirst()
                            .orElseThrow()
                            .verdict()
                            .name())
                    .as("대상군 " + e.getKey())
                    .isEqualTo(e.getValue().stringValue()));
    expect
        .path("preferences")
        .properties()
        .forEach(
            e ->
                assertThat(
                        judgment.preferences().stream()
                            .filter(p -> p.preference().id().equals(e.getKey()))
                            .findFirst()
                            .orElseThrow()
                            .verdict()
                            .name())
                    .as("우대 " + e.getKey())
                    .isEqualTo(e.getValue().stringValue()));
    expect
        .path("criteria")
        .properties()
        .forEach(
            e ->
                assertThat(found(byId, e.getKey()).verdict().name())
                    .as("조건 " + e.getKey())
                    .isEqualTo(e.getValue().stringValue()));
    expect
        .path("summaries")
        .properties()
        .forEach(
            e ->
                assertThat(found(byId, e.getKey()).summary())
                    .as("기준 설명 " + e.getKey())
                    .isEqualTo(e.getValue().stringValue()));
    expect
        .path("reasons")
        .properties()
        .forEach(
            e ->
                assertThat(found(byId, e.getKey()).reason())
                    .as("이유 " + e.getKey())
                    .isEqualTo(e.getValue().isNull() ? null : e.getValue().stringValue()));
    expect
        .path("criterionMissing")
        .properties()
        .forEach(
            e ->
                assertThat(fields(found(byId, e.getKey()).missing()))
                    .as("조건 " + e.getKey() + "의 부족한 입력")
                    .isEqualTo(strings(e.getValue())));
    if (expect.has("missingInputs")) {
      assertThat(fields(judgment.missingInputs()))
          .as("부족한 입력")
          .isEqualTo(strings(expect.get("missingInputs")));
    }
    expect
        .path("questions")
        .properties()
        .forEach(
            e -> {
              FrameJudgment.Question question =
                  judgment.questions().stream()
                      .filter(q -> q.id().equals(e.getKey()))
                      .findFirst()
                      .orElseThrow();
              String answer = question.answer() == null ? null : question.answer().name();
              assertThat(answer)
                  .as("질문 " + e.getKey())
                  .isEqualTo(e.getValue().isNull() ? null : e.getValue().stringValue());
            });
  }

  private static void index(Evaluation e, Map<String, Evaluation> byId) {
    byId.put(e.criterion().id(), e);
    e.options().forEach(o -> o.criteria().forEach(c -> index(c, byId)));
  }

  private static Evaluation found(Map<String, Evaluation> byId, String id) {
    assertThat(byId).as("조건 ID " + id).containsKey(id);
    return byId.get(id);
  }

  private static List<String> fields(List<Input> inputs) {
    return inputs.stream().map(Input::field).toList();
  }

  private static List<String> strings(JsonNode array) {
    List<String> values = new ArrayList<>();
    array.forEach(v -> values.add(v.stringValue()));
    return values;
  }

  private static List<Path> files(String field) {
    try (Stream<Path> paths =
        Files.list(
            Path.of(FrameCasesTest.class.getResource("/eligibility/frames/" + field).toURI()))) {
      return paths.filter(p -> p.toString().endsWith(".json")).sorted().toList();
    } catch (IOException | URISyntaxException e) {
      throw new IllegalStateException(e);
    }
  }
}
