package kr.mujuthaek.api.eligibility.mapper;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.Map;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.eligibility.dto.request.JudgmentApplicantRequest;
import kr.mujuthaek.api.eligibility.rule.frame.Applicant;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

/** 사용자 입력 읽기: 형식이 틀린 값은 400이고, 오류 메시지에 사용자가 넣은 값은 넣지 않아요. */
class ApplicantMapperTest {

  private static final JsonMapper JSON = JsonMapper.builder().build();

  private static JudgmentApplicantRequest request(String json) {
    return JSON.readValue(json, JudgmentApplicantRequest.class);
  }

  private static void invalid(String json, String at) {
    assertThatThrownBy(() -> ApplicantMapper.toApplicant(request(json), Map.of()))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> {
              assertThat(e.errorCode()).isEqualTo(ErrorCode.VALIDATION_FAILED);
              assertThat(e.getMessage()).startsWith(at);
            });
  }

  @Test
  void anEmptyRequestIsAnEmptyApplicant() {
    Applicant applicant = ApplicantMapper.toApplicant(null, null);
    assertThat(applicant.birthDate()).isNull();
    assertThat(applicant.statuses()).as("아직 고르지 않음").isNull();
    assertThat(applicant.answers()).isEmpty();
  }

  @Test
  void anEmptyStatusListMeansNoneApply() {
    Applicant applicant = ApplicantMapper.toApplicant(request("{\"statuses\": []}"), Map.of());
    assertThat(applicant.statuses()).isEmpty();
  }

  @Test
  void wrongRegionCodesAreRejectedWithoutEchoingThem() {
    assertThatThrownBy(
            () ->
                ApplicantMapper.toApplicant(
                    request("{\"residenceRegionCode\": \"123456789\"}"), Map.of()))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.getMessage()).contains("법정동코드").doesNotContain("123456789"));
  }

  @Test
  void negativeIncomeIsRejectedWithoutEchoingIt() {
    assertThatThrownBy(
            () ->
                ApplicantMapper.toApplicant(
                    request("{\"household\": {\"monthlyIncomeWon\": -4321987}}"), Map.of()))
        .isInstanceOfSatisfying(
            CustomException.class,
            e ->
                assertThat(e.getMessage())
                    .startsWith("profile.household.monthlyIncomeWon")
                    .doesNotContain("4321987"));
  }

  @Test
  void unknownStatusCodesAreRejected() {
    invalid("{\"statuses\": [\"VIP\"]}", "profile.statuses");
  }

  @Test
  void industryCodesHaveFiveDigits() {
    invalid("{\"business\": {\"industryCode\": \"561\"}}", "profile.business.industryCode");
  }

  @Test
  void aBusinessCannotCloseBeforeItOpens() {
    invalid(
        "{\"business\": {\"history\": [{\"openedOn\": \"2024-01-01\", \"closedOn\": \"2023-01-01\"}]}}",
        "profile.business.history");
  }
}
