package kr.mujuthaek.api.eligibility.dto.request;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import java.time.LocalDate;
import java.time.YearMonth;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

/**
 * 판정 요청의 날짜 범위 (2026-11-16 보안 감사 L-12). 「+999999999-12-31」 같은 날짜가 판정 계산(몇 년 더하기) 중 예외를 내서 400이 아닌
 * 500과 운영 경보가 났어요. 실제 날짜는 그대로 통과해야 해요.
 */
class RequestDateLimitsTest {

  private static final Validator VALIDATOR =
      Validation.buildDefaultValidatorFactory().getValidator();

  private static Set<String> paths(Object request) {
    Set<? extends ConstraintViolation<?>> violations = VALIDATOR.validate(request);
    return violations.stream().map(v -> v.getPropertyPath().toString()).collect(Collectors.toSet());
  }

  private static JudgmentApplicantRequest judgment(
      LocalDate birth, LocalDate married, List<LocalDate> children, LocalDate opened) {
    var business =
        new JudgmentApplicantRequest.BusinessRequest(
            null,
            null,
            null,
            List.of(new JudgmentApplicantRequest.BusinessRecordRequest(opened, null)),
            null,
            null);
    return new JudgmentApplicantRequest(
        birth, null, null, null, null, married, children, null, null, null, business, null, null,
        null, null);
  }

  @Test
  void realDatesPass() {
    var ok =
        new LoanEvaluateRequest(
            judgment(
                LocalDate.of(1990, 5, 1),
                LocalDate.of(2024, 3, 1),
                List.of(LocalDate.of(2025, 1, 1)),
                LocalDate.of(2020, 1, 1)),
            LocalDate.of(2026, 11, 16));
    assertThat(paths(ok)).isEmpty();
  }

  @Test
  void extremeDatesAreRejectedBeforeJudging() {
    LocalDate far = LocalDate.MAX;
    var bad =
        new LoanEvaluateRequest(
            judgment(LocalDate.MIN, far, List.of(LocalDate.of(2025, 1, 1), far), far), far);
    assertThat(paths(bad))
        .contains(
            "asOf",
            "profile.birthDate",
            "profile.marriedOn",
            "profile.childBirthDates[1].<list element>",
            "profile.business.history[0].openedOn");
  }

  @Test
  void yearMonthsAreBoundedToo() {
    var applicant =
        new JudgmentApplicantRequest(
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            YearMonth.of(1899, 12));
    assertThat(paths(new SpaceEvaluateRequest(applicant))).contains("applicant.birthMonth");
  }
}
