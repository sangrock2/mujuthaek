package kr.mujuthaek.api.eligibility.dto.request;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import java.time.LocalDate;
import java.time.YearMonth;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import kr.mujuthaek.api.eligibility.rule.Applicant;
import kr.mujuthaek.api.eligibility.rule.Bands;
import kr.mujuthaek.api.notice.NoticeFixtures;
import org.junit.jupiter.api.Test;

class ApplicantRequestTest {

  private static final Validator VALIDATOR =
      Validation.buildDefaultValidatorFactory().getValidator();

  static ApplicantRequest sample() {
    return new ApplicantRequest(
        LocalDate.of(1997, 3, 15),
        null,
        "11440",
        true,
        1,
        0,
        List.of("YOUTH"),
        "SINGLE",
        null,
        0,
        false,
        "3_5",
        new ApplicantRequest.SubscriptionRequest("24_PLUS", 26),
        List.of(),
        Map.of("URBAN_WORKER_INCOME", new ApplicantRequest.PercentRange(90, 100, null)),
        null,
        2026,
        new ApplicantRequest.WonRange(25_000_000L, 50_000_000L),
        null,
        List.of("R2_INCOME"));
  }

  @Test
  void everyFieldMayBeEmpty() {
    var empty =
        new ApplicantRequest(
            null, null, null, null, null, null, null, null, null, null, null, null, null, null,
            null, null, null, null, null, null);
    assertThat(VALIDATOR.validate(empty)).isEmpty();
    assertThat(empty.toApplicant()).isEqualTo(Applicant.empty());
  }

  @Test
  void readsTheBandJson() {
    String json =
        """
        {"birthDate":"1997-03-15","regionCode":"11440","householdHead":true,"householdSize":1,
         "dependents":0,"targetGroups":["YOUTH"],"marital":"SINGLE","marriedOn":null,"children":0,
         "homeOwner":false,"homelessYears":"3_5","subscription":{"months":"24_PLUS","payments":26},
         "welfareStatuses":[],"income":{"URBAN_WORKER_INCOME":{"gtPct":90,"lePct":100}},
         "incomeYear":2026,"assets":{"gtWon":25000000,"leWon":50000000},"rankChecks":["R2_INCOME"],
         "workplace":{"label":"여의도역","lat":37.5216,"lng":126.9243},"priorities":{"work":8}}""";

    assertThat(NoticeFixtures.JSON.readValue(json, ApplicantRequest.class)).isEqualTo(sample());
  }

  @Test
  void stillReadsTheBirthMonthOfOlderScreens() {
    var old = NoticeFixtures.JSON.readValue("{\"birthMonth\":\"1997-03\"}", ApplicantRequest.class);

    Applicant a = old.toApplicant();
    assertThat(a.birthDate()).isNull();
    assertThat(a.birthMonth()).isEqualTo(YearMonth.of(1997, 3));
    // 기준일이 생일 달이면 출생 연월로는 나이가 둘이에요
    assertThat(a.ages(LocalDate.of(2026, 3, 10))).containsExactly(28, 29);
    assertThat(sample().toApplicant().ages(LocalDate.of(2026, 3, 10))).containsExactly(28, 28);
  }

  @Test
  void bandsBecomeRanges() {
    Applicant a = sample().toApplicant();
    assertThat(a.homelessYears()).isEqualTo(new Bands.Span(3, 5, false));
    assertThat(a.subscription().months()).isEqualTo(new Bands.Span(24, null, false));
    assertThat(a.personalIncome()).containsEntry("URBAN_WORKER_INCOME", new Bands.Range(90L, 100L));
    assertThat(a.assets()).isEqualTo(new Bands.Range(25_000_000L, 50_000_000L));
  }

  @Test
  void rejectsMalformedValuesByFieldName() {
    var bad =
        new ApplicantRequest(
            LocalDate.now().plusDays(1),
            YearMonth.now().plusMonths(1),
            "1144",
            null,
            0,
            -1,
            List.of("STUDENT"),
            "DIVORCED",
            null,
            null,
            null,
            "2_4",
            new ApplicantRequest.SubscriptionRequest("3_YEARS", -3),
            List.of("RICH"),
            Map.of("MEDIAN_INCOME", new ApplicantRequest.PercentRange(100, 90, 1999)),
            null,
            1999,
            new ApplicantRequest.WonRange(-1L, null),
            new ApplicantRequest.WonRange(10L, 5L),
            List.of("R9"));

    Set<String> fields =
        VALIDATOR.validate(bad).stream()
            .map(v -> v.getPropertyPath().toString().replaceAll("\\[\\w*]\\.<.*>", ""))
            .collect(Collectors.toSet());
    assertThat(fields)
        .contains(
            "birthDate",
            "birthMonth",
            "regionCode",
            "householdSize",
            "dependents",
            "targetGroups",
            "marital",
            "homelessYears",
            "subscription.months",
            "subscription.payments",
            "welfareStatuses",
            "income[MEDIAN_INCOME].ordered",
            "income[MEDIAN_INCOME].year",
            "incomeYear",
            "assets.gtWon",
            "car.ordered",
            "rankChecks");
  }

  @Test
  void toStringHidesIncomeAssetsAndBirthDate() {
    String text = sample().toString();

    assertThat(text)
        .startsWith("ApplicantRequest[")
        .contains("regionCode=11440", "birthDate=***", "personalIncome=***", "assets=***")
        .doesNotContain("1997-03", "gt=90", "25000000", "R2_INCOME");
    assertThat(sample().toApplicant().toString())
        .contains("birthDate=***")
        .doesNotContain("1997-03");
  }

  @Test
  void singlePersonHouseholdIncomeIsThePersonalIncome() {
    assertThat(sample().toApplicant().householdIncomeOrSelf())
        .containsEntry("URBAN_WORKER_INCOME", new Bands.Range(90L, 100L));
  }
}
