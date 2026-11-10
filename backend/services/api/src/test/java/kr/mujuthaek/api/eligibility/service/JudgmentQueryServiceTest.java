package kr.mujuthaek.api.eligibility.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.List;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.eligibility.dto.request.JudgmentApplicantRequest;
import kr.mujuthaek.api.eligibility.dto.request.SpaceEvaluateRequest;
import kr.mujuthaek.api.eligibility.model.JudgmentResult;
import kr.mujuthaek.api.eligibility.model.MissingInput;
import kr.mujuthaek.api.eligibility.rule.Eligibility;
import kr.mujuthaek.api.eligibility.rule.Verdict;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * 틀 하나 판정 서비스를 실제 스프링·DB(Testcontainers, 기준값 마이그레이션)로 불러요. 틀 + 입력 → 정제된 결과, 오류 코드까지 봐요. 결과에 사용자가 넣은
 * 값이 없는지도 봐요.
 */
@SpringBootTest
@Import(TestcontainersConfiguration.class)
class JudgmentQueryServiceTest {

  private static final JsonMapper JSON = JsonMapper.builder().build();

  @Autowired private JudgmentQueryService judgments;
  @Autowired private JsonMapper mapper;

  /** 정답 케이스 파일의 틀 (정의서 예시 그대로). */
  private static JsonNode frame(String file) throws IOException {
    try (InputStream in =
        JudgmentQueryServiceTest.class.getResourceAsStream(
            "/eligibility/frames/" + file + ".json")) {
      return JSON.readTree(new String(in.readAllBytes(), StandardCharsets.UTF_8)).get("frame");
    }
  }

  private static JudgmentApplicantRequest applicant(String json) {
    return JSON.readValue(json, JudgmentApplicantRequest.class);
  }

  private static void rejected(Runnable call, ErrorCode code, String detail) {
    assertThatThrownBy(call::run)
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> {
              assertThat(e.errorCode()).isEqualTo(code);
              assertThat(e.getMessage()).contains(detail);
            });
  }

  @Test
  void housingJudgesTheSeoripulNotice() throws Exception {
    JudgmentApplicantRequest applicant =
        applicant(
            """
            {"birthDate": "1999-05-05", "residenceRegionCode": "1165000000",
             "household": {"size": 1, "homeless": true, "monthlyIncomeWon": 3000000}}""");

    JudgmentResult result = judgments.judgeHousing(frame("housing/seoripul-artown"), applicant);

    assertThat(result.field()).isEqualTo("HOUSING");
    // 예술인 증명은 공고마다 묻지 않고 원문 확인이라, 나머지가 다 맞아도 확인 필요예요 (2026-10-29 결정)
    assertThat(result.result()).isEqualTo(Eligibility.NEEDS_INPUT);
    assertThat(result.referenceDate()).isEqualTo(LocalDate.parse("2026-10-16"));
    JudgmentResult.Group artist = result.groups().getFirst();
    assertThat(artist.id()).isEqualTo("artist");
    assertThat(artist.result()).isEqualTo(Eligibility.NEEDS_INPUT);
    JudgmentResult.Criterion artsProof = artist.criteria().getFirst();
    assertThat(artsProof.id()).isEqualTo("arts-proof");
    assertThat(artsProof.result()).isEqualTo(Verdict.UNKNOWN);
    assertThat(artsProof.reason()).isEqualTo("원문 조건을 확인해 주세요");
    JudgmentResult.Criterion incomeOrAssets = artist.criteria().get(4);
    assertThat(incomeOrAssets.kind()).isEqualTo("ANY_OF");
    assertThat(incomeOrAssets.options().get(1).result()).isEqualTo(Verdict.MET);
    assertThat(incomeOrAssets.options().get(1).criteria().getFirst().summary())
        .isEqualTo("세대 월소득 3,432,027원 이하 (도시근로자 가구원수별 월평균소득 2025년 1인 × 90%)");
    assertThat(result.notes().getFirst().kind()).isEqualTo("RULE");
    assertThat(result.missingInputs()).isEmpty(); // 더 넣을 입력이 아니라 원문을 볼 조건이에요
    // 결과에는 사용자가 넣은 값(소득·생년월일)이 없어요
    assertThat(JSON.writeValueAsString(result))
        .doesNotContain("3,000,000")
        .doesNotContain("1999-05-05");
  }

  @Test
  void anEmptyApplicantGetsTheMissingInputs() throws Exception {
    JudgmentResult result = judgments.judgeHousing(frame("housing/seoripul-artown"), null);

    assertThat(result.result()).isEqualTo(Eligibility.NEEDS_INPUT);
    assertThat(result.missingInputs())
        .extracting(MissingInput::field)
        .contains("household.monthlyIncomeWon", "birthDate");
  }

  @Test
  void eachUndecidedCriterionSaysWhichInputWouldDecideIt() throws Exception {
    // 2026-10-29 QA: 검수 중이라 확인 필요인 조건에도 화면이 「입력」을 붙였어요. 주거·혜택처럼 조건마다 needs를 줘요
    JsonNode frame =
        JSON.readTree(
            """
            {"schema":"business-space-judgment.v1","rawPostId":"p","rawVersion":1,"referenceDate":"2026-10-28",
             "common":[
               {"id":"age","kind":"AGE","quote":null,"page":null,"inReview":false,"reviewReason":null,"minAge":19,"maxAge":49},
               {"id":"reviewing","kind":"AGE","quote":null,"page":null,"inReview":true,"reviewReason":"표기가 두 가지","minAge":19,"maxAge":49},
               {"id":"branch","kind":"ASK","quote":null,"page":null,"inReview":false,"reviewReason":null,"question":"지사로 입주하나요?","metWhen":"NO"}],
             "groups":[{"id":"all","name":"전체","criteria":[]}],"preferences":[],"notes":[]}""");

    JudgmentResult empty = judgments.judgeBusinessSpace(frame, null);
    assertThat(empty.common())
        .extracting(JudgmentResult.Criterion::needs)
        .containsExactly(List.of("birthDate"), List.of(), List.of()); // 검수 중·질문은 넣을 입력이 없어요

    JudgmentResult born =
        judgments.judgeBusinessSpace(frame, applicant("{\"birthDate\": \"1992-07-15\"}"));
    assertThat(born.common().getFirst().result()).isEqualTo(Verdict.MET);
    assertThat(born.common()).extracting(JudgmentResult.Criterion::needs).allMatch(List::isEmpty);
  }

  @Test
  void businessAgeQuestionIsJudgedFromTheBusinessHistory() throws Exception {
    // 2026-10-29 QA: 「창업 7년 이내」가 업력을 넣어도 질문으로만 남아 확인 필요였어요
    JsonNode frame =
        JSON.readTree(
            """
            {"schema":"business-space-judgment.v1","rawPostId":"p","rawVersion":1,"referenceDate":"2026-10-28",
             "common":[],"preferences":[],"notes":[],
             "groups":[{"id":"young","name":"창업 7년 이내 기업","criteria":[
               {"id":"registered","kind":"BUSINESS_REGISTRATION","require":"REGISTERED","closedWithinYears":null},
               {"id":"age-7y","kind":"ASK","question":"사업을 시작한 날(법인은 설립등기일)부터 7년 이내인가요?","metWhen":"YES"}]}]}""");

    JudgmentResult result =
        judgments.judgeBusinessSpace(
            frame, applicant("{\"business\": {\"history\": [{\"openedOn\": \"2024-03-01\"}]}}"));

    assertThat(result.result()).isEqualTo(Eligibility.ELIGIBLE);
    JudgmentResult.Criterion age = result.groups().getFirst().criteria().get(1);
    assertThat(age.kind()).isEqualTo("BUSINESS_AGE");
    assertThat(age.result()).isEqualTo(Verdict.MET);
  }

  @Test
  void businessSpaceJudgesTheYangsanNotice() throws Exception {
    JudgmentApplicantRequest applicant =
        applicant(
            """
            {"birthDate": "1996-02-01", "korean": true,
             "business": {"applicantType": "INDIVIDUAL", "history": [], "industryCode": "56111"},
             "statuses": [], "restrictions": []}""");
    JudgmentResult result =
        judgments.judgeBusinessSpace(frame("business-space/yangsan-hope-shop"), applicant);

    assertThat(result.field()).isEqualTo("BUSINESS_SPACE");
    // 실제 사용·창업 아이디어 같은 질문은 원문 확인이라, 입력으로 정하는 조건이 다 맞아도 청년 길은 확인 필요예요
    assertThat(result.result()).isEqualTo(Eligibility.NEEDS_INPUT);
    assertThat(result.groups().getFirst().id()).isEqualTo("youth");
    assertThat(result.groups().getFirst().result()).isEqualTo(Eligibility.NEEDS_INPUT);
    assertThat(result.common())
        .filteredOn(c -> c.kind().equals("ASK"))
        .extracting(JudgmentResult.Criterion::reason)
        .containsOnly("원문 조건을 확인해 주세요");
    assertThat(result.missingInputs()).isEmpty();
  }

  @Test
  void startupSupportShowsPreferencesSeparately() throws Exception {
    JudgmentApplicantRequest applicant =
        applicant(
            """
            {"birthDate": "1993-04-10", "business": {"history": [{"openedOn": "2024-05-02"}], "industryCode": "58222"},
             "statuses": ["SME"], "restrictions": []}""");
    JudgmentResult result =
        judgments.judgeStartupSupport(frame("startup-support/early-startup-package"), applicant);

    assertThat(result.result()).isEqualTo(Eligibility.NEEDS_INPUT); // 질문 조건은 원문 확인
    JudgmentResult.Preference award = result.preferences().getFirst();
    assertThat(award.id()).isEqualTo("ces-award");
    assertThat(award.result()).isEqualTo(Verdict.UNKNOWN); // 우대 질문도 원문 확인
    assertThat(award.points()).isEqualByComparingTo("2");
  }

  @Test
  void anOldScreenSendingAnswersStillWorks() {
    // 예전 화면은 질문 답(answers)을 보냈어요. 이제 받지 않지만 요청이 깨지면 안 돼요 (2026-10-29)
    SpaceEvaluateRequest request =
        mapper.readValue(
            """
            {"applicant": {"birthDate": "1996-02-01"}, "answers": {"real-use": "YES"}}""",
            SpaceEvaluateRequest.class);
    assertThat(request.applicant()).isNotNull();
  }

  @Test
  void aFrameOfAnotherFieldIsRejected() throws Exception {
    JsonNode housing = frame("housing/seoripul-artown");
    rejected(
        () -> judgments.judgeBusinessSpace(housing, null),
        ErrorCode.ELIGIBILITY_FIELD_MISMATCH,
        "housing-judgment.v1");
  }

  @Test
  void aBrokenFrameSaysWhereItIsBroken() {
    JsonNode frame =
        JSON.readTree(
            """
            {"schema": "housing-judgment.v1", "rawPostId": "p", "rawVersion": 1, "referenceDate": "2026-10-16",
             "groups": [{"id": "g", "name": "전체", "criteria": [{"id": "x", "kind": "REVENUE"}]}]}""");
    rejected(
        () -> judgments.judgeHousing(frame, null),
        ErrorCode.ELIGIBILITY_INVALID_FRAME,
        "frame.groups[0].criteria[0].kind");
  }

  @Test
  void aWrongApplicantValueIsRejectedWithoutEchoingIt() throws Exception {
    JsonNode frame = frame("housing/seoripul-artown");
    JudgmentApplicantRequest applicant =
        applicant("{\"household\": {\"monthlyIncomeWon\": -7654321}}");
    rejected(
        () -> judgments.judgeHousing(frame, applicant),
        ErrorCode.VALIDATION_FAILED,
        "profile.household.monthlyIncomeWon");
    assertThatThrownBy(() -> judgments.judgeHousing(frame, applicant))
        .hasMessageNotContaining("7654321");
  }

  @Test
  void theFrameIsRequired() {
    rejected(() -> judgments.judgeHousing(null, null), ErrorCode.VALIDATION_FAILED, "frame");
  }
}
