package kr.mujuthaek.api.eligibility.mapper;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.eligibility.rule.Field;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion;
import kr.mujuthaek.api.eligibility.rule.frame.Frame;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** 판정 틀 읽기: 형식이 틀리면 어느 칸이 왜 틀렸는지 400으로 알려줘요. */
class FrameReaderTest {

  private static final JsonMapper JSON = JsonMapper.builder().build();

  private static JsonNode housing(String criteria) {
    return JSON.readTree(
        """
        {"schema": "housing-judgment.v1", "rawPostId": "p1", "rawVersion": 1,
         "referenceDate": "2026-10-16", "common": [],
         "groups": [{"id": "g", "name": "전체", "criteria": [%s]}], "notes": []}"""
            .formatted(criteria));
  }

  private static void invalid(JsonNode frame, FrameSpec spec, String detail) {
    assertThatThrownBy(() -> FrameReader.read(frame, spec))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> {
              assertThat(e.errorCode()).isEqualTo(ErrorCode.ELIGIBILITY_INVALID_FRAME);
              assertThat(e.getMessage()).contains(detail);
            });
  }

  private static String ask(String id, String question, String metWhen) {
    return """
        {"id": "%s", "kind": "ASK", "question": "%s", "metWhen": "%s"}"""
        .formatted(id, question, metWhen);
  }

  @Test
  void businessAgeQuestionsAreReadAsBusinessAgeYears() {
    // 2026-10-29 QA: 사업공간 틀에는 업력 칸이 없어 「창업 N년 이내」가 질문으로 와요. 추출 문구 그대로면 업력 햇수로 읽어요
    String q = "사업을 시작한 날(법인은 설립등기일)부터 ";
    Frame frame =
        FrameReader.read(
            JSON.readTree(
                """
                {"schema": "business-space-judgment.v1", "rawPostId": "p1", "rawVersion": 1,
                 "referenceDate": "2026-10-28", "common": [], "preferences": [], "notes": [],
                 "groups": [{"id": "g", "name": "창업 7년 이내 기업", "criteria": [%s, %s, %s, %s, %s, %s]}]}"""
                    .formatted(
                        ask("within", q + "7년 이내인가요?", "YES"),
                        ask("under", q + "3년이 지나지 않았나요?", "YES"),
                        ask("at-least", q + "2년 이상 지났나요?", "YES"),
                        ask("over", q + "1년이 넘게 지났나요?", "YES"),
                        ask("no-means-met", q + "7년 이내인가요?", "NO"),
                        ask("branch", "지사로 입주하나요?", "NO"))),
            FrameSpec.BUSINESS_SPACE);
    var criteria = frame.groups().getFirst().criteria();
    assertThat(criteria)
        .extracting(Criterion::kind)
        .containsExactly(
            "BUSINESS_AGE", "BUSINESS_AGE", "BUSINESS_AGE", "BUSINESS_AGE", "ASK", "ASK");
    assertThat(criteria.subList(0, 4))
        .extracting(c -> (Criterion.BusinessAgeYears) c)
        .extracting(c -> c.years() + " " + c.rule())
        .containsExactly("7 WITHIN", "3 UNDER", "2 AT_LEAST", "1 OVER");
    assertThat(criteria.getFirst().id()).isEqualTo("within"); // 같은 ID·근거를 그대로 써요
  }

  @Test
  void onlyStartupSupportFramesMayLeaveTheReferenceDateEmpty() {
    // 창업지원 공고에 기준일 문구가 없으면 null로 받고, 판정하는 날 기준으로 계산해요
    Frame startup =
        FrameReader.read(
            JSON.readTree(
                """
                {"schema": "startup-support-judgment.v1", "rawPolicyId": "p1", "rawVersion": 1,
                 "referenceDate": null, "common": [], "preferences": [], "notes": [],
                 "groups": [{"id": "g", "name": "전체", "criteria": [
                   {"id": "s", "kind": "STATUS", "anyOf": ["STUDENT", "ONE_PERSON_CREATIVE", "DISABLED"]}]}]}"""),
            FrameSpec.STARTUP_SUPPORT);
    assertThat(startup.referenceDate()).isNull();
    // 주거·사업공간 틀은 기준일이 꼭 있어야 해요
    invalid(
        JSON.readTree(housing("").toString().replace("\"2026-10-16\"", "null")),
        FrameSpec.HOUSING,
        "frame.referenceDate: 값이 있어야 해요");
  }

  @Test
  void savingsCanUseTheDepositTableButNotTogetherWithAFixedBalance() {
    Frame frame =
        FrameReader.read(
            housing(
                """
                {"id": "s", "kind": "SAVINGS", "minMonths": 24, "minPayments": null,
                 "minBalanceWon": null, "depositAreaM2": 114.92}"""),
            FrameSpec.HOUSING);
    Criterion.Savings savings = (Criterion.Savings) frame.groups().getFirst().criteria().getFirst();
    assertThat(savings.depositAreaM2()).isEqualByComparingTo("114.92");
    // depositAreaM2는 v1에 나중에 더한 칸이라 없어도 돼요
    Criterion.Savings old =
        (Criterion.Savings)
            FrameReader.read(
                    housing("{\"id\": \"s\", \"kind\": \"SAVINGS\", \"minMonths\": 6}"),
                    FrameSpec.HOUSING)
                .groups()
                .getFirst()
                .criteria()
                .getFirst();
    assertThat(old.depositAreaM2()).isNull();
    invalid(
        housing(
            "{\"id\": \"s\", \"kind\": \"SAVINGS\", \"minBalanceWon\": 3000000, \"depositAreaM2\": 90}"),
        FrameSpec.HOUSING,
        "frame.groups[0].criteria[0].depositAreaM2");
    invalid(
        housing("{\"id\": \"s\", \"kind\": \"SAVINGS\", \"depositAreaM2\": 0}"),
        FrameSpec.HOUSING,
        "0보다 큰 숫자여야 해요");
  }

  @Test
  void readsAValidFrame() {
    Frame frame =
        FrameReader.read(
            housing(
                """
                {"id": "age", "kind": "AGE", "minAge": 19, "maxAge": 39},
                {"id": "seoul", "kind": "RESIDENCE", "regionCodes": ["1100000000"], "minMonths": null}"""),
            FrameSpec.HOUSING);
    assertThat(frame.field()).isEqualTo(Field.HOUSING);
    assertThat(frame.groups().getFirst().criteria())
        .extracting(Criterion::kind)
        .containsExactly("AGE", "RESIDENCE");
    // quote·page·inReview는 없어도 돼요
    assertThat(frame.groups().getFirst().criteria().getFirst().meta().inReview()).isFalse();
  }

  @Test
  void anotherFieldsFrameIsAFieldMismatch() {
    assertThatThrownBy(() -> FrameReader.read(housing(""), FrameSpec.BUSINESS_SPACE))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> {
              assertThat(e.errorCode()).isEqualTo(ErrorCode.ELIGIBILITY_FIELD_MISMATCH);
              assertThat(e.getMessage())
                  .contains("business-space-judgment.v1", "housing-judgment.v1");
            });
  }

  @Test
  void kindsOfAnotherFieldAreRejectedWithThePath() {
    invalid(
        housing("{\"id\": \"x\", \"kind\": \"INDUSTRY\"}"),
        FrameSpec.HOUSING,
        "frame.groups[0].criteria[0].kind: housing-judgment.v1 틀에서 쓸 수 없는 종류예요: INDUSTRY");
  }

  @Test
  void duplicateIdsAreRejected() {
    invalid(
        housing(
            """
            {"id": "g", "kind": "AGE", "minAge": 19}"""),
        FrameSpec.HOUSING,
        "ID가 겹쳐요: g");
  }

  @Test
  void bothAgeBoundsEmptyIsRejected() {
    invalid(
        housing("{\"id\": \"a\", \"kind\": \"AGE\", \"minAge\": null, \"maxAge\": null}"),
        FrameSpec.HOUSING,
        "minAge와 maxAge가 둘 다 비어 있어요");
  }

  @Test
  void regionCodesMustHaveTenDigits() {
    invalid(
        housing("{\"id\": \"r\", \"kind\": \"RESIDENCE\", \"regionCodes\": [\"11\"]}"),
        FrameSpec.HOUSING,
        "frame.groups[0].criteria[0].regionCodes[0]: 형식이 맞지 않아요");
  }

  @Test
  void newbornBonusNeedsADateAndACountRule() {
    invalid(
        housing(
            """
            {"id": "i", "kind": "INCOME", "basis": "HOUSEHOLD", "standard": "MEDIAN_INCOME",
             "year": 2026, "percent": 150, "bonusCombine": "SUM", "printedTable": [],
             "bonuses": [{"when": {"factor": "NEWBORN_CHILDREN", "min": 1, "max": 1}, "addPercent": 10}]}"""),
        FrameSpec.HOUSING,
        "since와 countRule이 있어야 해요");
  }

  @Test
  void incomeWithoutStandardNeedsAPrintedTable() {
    invalid(
        housing(
            """
            {"id": "i", "kind": "INCOME", "basis": "HOUSEHOLD", "standard": null,
             "year": null, "percent": null, "bonuses": [], "printedTable": []}"""),
        FrameSpec.HOUSING,
        "공고 금액표가 있어야 해요");
  }

  @Test
  void statusCodesOfAnotherFieldAreRejected() {
    invalid(
        housing("{\"id\": \"s\", \"kind\": \"STATUS\", \"anyOf\": [\"SMALL_BUSINESS\"]}"),
        FrameSpec.HOUSING,
        "쓸 수 없는 유형 코드예요: SMALL_BUSINESS");
  }

  @Test
  void asOfIsOnlyForStartupSupportFrames() {
    invalid(
        housing("{\"id\": \"a\", \"kind\": \"AGE\", \"minAge\": 19, \"asOf\": \"2026-01-22\"}"),
        FrameSpec.HOUSING,
        "조건별 기준일(asOf)이 없어요");
  }

  @Test
  void housingFramesHaveNoPreferences() {
    JsonNode frame =
        JSON.readTree(
            """
            {"schema": "housing-judgment.v1", "rawPostId": "p", "rawVersion": 1,
             "referenceDate": "2026-10-16", "groups": [{"id": "g", "name": "전체", "criteria": []}],
             "preferences": [{"id": "p1"}]}""");
    invalid(frame, FrameSpec.HOUSING, "우대(preferences)가 없어요");
  }

  @Test
  void groupsMayHaveARankStartingAtOne() {
    JsonNode frame =
        JSON.readTree(
            """
            {"schema": "housing-judgment.v1", "rawPostId": "p", "rawVersion": 1,
             "referenceDate": "2026-10-16", "groups": [
               {"id": "first", "name": "1순위", "rank": 1, "criteria": []},
               {"id": "plain", "name": "순위 없음", "rank": null, "criteria": []},
               {"id": "old", "name": "rank 칸 없음", "criteria": []}]}""");
    assertThat(FrameReader.read(frame, FrameSpec.HOUSING).groups())
        .extracting(Frame.Group::rank)
        .containsExactly(1, null, null);

    JsonNode zero =
        JSON.readTree(
            """
            {"schema": "business-space-judgment.v1", "rawPostId": "p", "rawVersion": 1,
             "referenceDate": "2026-10-12", "groups": [{"id": "g", "name": "전체", "rank": 0, "criteria": []}]}""");
    invalid(zero, FrameSpec.BUSINESS_SPACE, "frame.groups[0].rank: 1 이상이어야 해요");
  }

  @Test
  void startupFramesHaveNoRank() {
    JsonNode frame =
        JSON.readTree(
            """
            {"schema": "startup-support-judgment.v1", "rawPolicyId": "p", "rawVersion": 1,
             "referenceDate": "2026-01-23", "groups": [{"id": "g", "name": "전체", "rank": 1, "criteria": []}]}""");
    invalid(
        frame,
        FrameSpec.STARTUP_SUPPORT,
        "frame.groups[0].rank: startup-support-judgment.v1 틀에는 신청 순위(rank)가 없어요");
  }

  @Test
  void aFrameNeedsAtLeastOneGroup() {
    JsonNode frame =
        JSON.readTree(
            """
            {"schema": "housing-judgment.v1", "rawPostId": "p", "rawVersion": 1,
             "referenceDate": "2026-10-16", "groups": []}""");
    invalid(frame, FrameSpec.HOUSING, "frame.groups: 대상군이 하나 이상 있어야 해요");
  }

  @Test
  void closedWithinYearsIsOnlyForClosedRegistrations() {
    JsonNode frame =
        JSON.readTree(
            """
            {"schema": "business-space-judgment.v1", "rawPostId": "p", "rawVersion": 1,
             "referenceDate": "2026-10-12", "groups": [{"id": "g", "name": "전체", "criteria": [
               {"id": "r", "kind": "BUSINESS_REGISTRATION", "require": "REGISTERED", "closedWithinYears": 10}]}]}""");
    invalid(frame, FrameSpec.BUSINESS_SPACE, "폐업 기간은 CLOSED일 때만 넣어요");
  }

  @Test
  void startupFramesHaveNoClosedRegistration() {
    JsonNode frame =
        JSON.readTree(
            """
            {"schema": "startup-support-judgment.v1", "rawPolicyId": "p", "rawVersion": 1,
             "referenceDate": "2026-01-23", "groups": [{"id": "g", "name": "전체", "criteria": [
               {"id": "r", "kind": "BUSINESS_REGISTRATION", "require": "CLOSED"}]}]}""");
    invalid(
        frame, FrameSpec.STARTUP_SUPPORT, "startup-support-judgment.v1 틀에서 쓸 수 없는 값이에요: CLOSED");
  }

  @Test
  void pointsAreOnlyForBonusPoints() {
    JsonNode frame =
        JSON.readTree(
            """
            {"schema": "startup-support-judgment.v1", "rawPolicyId": "p", "rawVersion": 1,
             "referenceDate": "2026-01-23", "groups": [{"id": "g", "name": "전체", "criteria": []}],
             "preferences": [{"id": "p1", "label": "우선", "effect": "PRIORITY", "points": 3,
               "criteria": [{"id": "q", "kind": "ASK", "question": "?", "metWhen": "YES"}]}]}""");
    invalid(frame, FrameSpec.STARTUP_SUPPORT, "점수는 가점(BONUS_POINTS)일 때만 넣어요");
  }
}
