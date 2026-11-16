package kr.mujuthaek.api.eligibility.dto.request;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import java.time.LocalDate;
import java.util.Collections;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

/**
 * 로그인 없이 부르는 맞춤 목록·판정 요청의 목록 길이 상한 (2026-11-16 보안 감사 H-2·H-3). 상한이 없으면 1MB 요청 하나에 지역 코드 수십만 개를 넣어
 * DB·CPU를 오래 붙잡을 수 있었어요. 화면이 보내는 크기(지역 1개, 관심 지역 30개까지)는 그대로 통과해야 해요.
 */
class RequestListLimitsTest {

  private static final Validator VALIDATOR =
      Validation.buildDefaultValidatorFactory().getValidator();

  private static List<String> codes(int n) {
    return IntStream.range(0, n).mapToObj(i -> String.valueOf(11000 + i)).toList();
  }

  private static Set<String> paths(Object request) {
    Set<? extends ConstraintViolation<?>> violations = VALIDATOR.validate(request);
    return violations.stream().map(v -> v.getPropertyPath().toString()).collect(Collectors.toSet());
  }

  private static JudgmentApplicantRequest judgment(
      List<LocalDate> children, JudgmentApplicantRequest.BusinessRequest business) {
    return new JudgmentApplicantRequest(
        null, null, null, null, null, null, children, null, null, null, business, null, null, null,
        null);
  }

  private static JudgmentApplicantRequest.BusinessRequest business(int records) {
    var history =
        Collections.nCopies(
            records,
            new JudgmentApplicantRequest.BusinessRecordRequest(LocalDate.of(2020, 1, 1), null));
    return new JudgmentApplicantRequest.BusinessRequest(null, null, null, history, null, null);
  }

  @Test
  void benefitSearchAcceptsFiftyRegionsAndRejectsMore() {
    var ok =
        new BenefitSearchRequest(
            new BenefitSearchRequest.Filters(codes(50), List.of("HOUSING"), null),
            null,
            null,
            null,
            null);
    var tooMany =
        new BenefitSearchRequest(
            new BenefitSearchRequest.Filters(codes(51), null, null), null, null, null, null);

    assertThat(paths(ok)).isEmpty();
    assertThat(paths(tooMany)).containsExactly("filters.regionCodes");
  }

  @Test
  void noticeFiltersAreBoundedForSearchAndHomeSummary() {
    var tooMany = new NoticeSearchRequest.Filters(null, codes(51), null, null, null, null, null);
    var hugeProvider =
        new NoticeSearchRequest.Filters(
            null, null, null, null, List.of("가".repeat(101)), null, null);

    assertThat(paths(new NoticeSearchRequest(tooMany, null, null, null, null, null)))
        .containsExactly("filters.regionCodes");
    assertThat(paths(new HomeSummaryRequest(tooMany, null))).containsExactly("filters.regionCodes");
    assertThat(paths(new HomeSummaryRequest(hugeProvider, null)))
        .containsExactly("filters.providers[0].<list element>");
    assertThat(
            paths(
                new HomeSummaryRequest(
                    new NoticeSearchRequest.Filters(
                        null, codes(30), null, List.of("PUBLIC_RENTAL"), null, null, null),
                    null)))
        .isEmpty();
  }

  @Test
  void supportAndSpaceSearchBoundRegionsAndBusinessHistory() {
    var supportRegions =
        new SupportSearchRequest(
            new SupportSearchRequest.Filters(null, codes(51), null), null, null, null, null, null);
    var spaceRegions =
        new SpaceSearchRequest(
            new SpaceSearchRequest.Filters(null, codes(51), null), null, null, null, null, null);
    var longHistory =
        new SupportSearchRequest(null, judgment(null, business(51)), null, null, null, null);
    var normal =
        new SpaceSearchRequest(
            new SpaceSearchRequest.Filters(List.of("STARTUP_SPACE"), codes(1), null),
            judgment(List.of(LocalDate.of(2020, 5, 1)), business(1)),
            null,
            null,
            null,
            null);

    assertThat(paths(supportRegions)).containsExactly("filters.regionCodes");
    assertThat(paths(spaceRegions)).containsExactly("filters.regionCodes");
    assertThat(paths(longHistory)).containsExactly("applicant.business.history");
    assertThat(paths(normal)).isEmpty();
  }

  @Test
  void loanAndNoticeApplicantListsAreBounded() {
    var manyChildren =
        new LoanEvaluateRequest(
            judgment(Collections.nCopies(21, LocalDate.of(2020, 1, 1)), null), null);
    var manyRankChecks =
        new ApplicantRequest(
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
            null,
            null,
            null,
            null,
            null,
            Collections.nCopies(51, "R2_INCOME"));

    assertThat(paths(manyChildren)).containsExactly("profile.childBirthDates");
    assertThat(paths(manyRankChecks)).containsExactly("rankChecks");
  }
}
