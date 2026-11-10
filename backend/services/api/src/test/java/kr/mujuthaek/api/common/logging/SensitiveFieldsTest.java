package kr.mujuthaek.api.common.logging;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.PrintWriter;
import java.io.StringWriter;
import org.junit.jupiter.api.Test;

class SensitiveFieldsTest {

  @Test
  void masksJsonValues() {
    String json =
        """
        {"applicant":{"birthDate":"1997-03-15","regionCode":"11440",
         "personalIncomeAnnualWon":32000000,"totalAssetsWon": 45000000,
         "welfareStatuses":["NEAR_POOR"],"carValueWon":null,"children":0}}""";

    String masked = SensitiveFields.mask(json);

    assertThat(masked)
        .doesNotContain("1997-03-15", "32000000", "45000000", "NEAR_POOR")
        .contains(
            "\"birthDate\":\"***\"",
            "\"personalIncomeAnnualWon\":\"***\"",
            "\"totalAssetsWon\": \"***\"",
            "\"welfareStatuses\":\"***\"",
            "\"regionCode\":\"11440\"",
            "\"children\":0");
  }

  @Test
  void masksRecordToString() {
    String text =
        "Applicant[birthDate=1997-03-15, regionCode=11440, personalIncomeAnnualWon=32000000,"
            + " rankChecks=[R2_INCOME, R2_ASSET], availableCashWon=15000000]";

    assertThat(SensitiveFields.mask(text))
        .isEqualTo(
            "Applicant[birthDate=***, regionCode=11440, personalIncomeAnnualWon=***,"
                + " rankChecks=***, availableCashWon=***]");
  }

  @Test
  void masksBandObjectsAndMapsToo() {
    String json =
        """
        {"applicant":{"birthMonth":"1997-03","income":{"MEDIAN_INCOME":{"gtPct":50,"lePct":60}},
         "assets": {"gtWon":215000000,"leWon":251000000},"children":0}}""";
    assertThat(SensitiveFields.mask(json))
        .doesNotContain("1997-03", "gtPct", "215000000")
        .contains(
            "\"birthMonth\":\"***\"",
            "\"income\":\"***\"",
            "\"assets\": \"***\"",
            "\"children\":0");

    String text =
        "Applicant[birthMonth=1997-03, personalIncome={MEDIAN_INCOME=Range[gt=50, le=60],"
            + " URBAN_WORKER_INCOME=Range[gt=90, le=100]}, assets=Range[gt=1, le=2], children=0]";
    assertThat(SensitiveFields.mask(text))
        .isEqualTo("Applicant[birthMonth=***, personalIncome=***, assets=***, children=0]");
  }

  @Test
  void leavesOtherTextAlone() {
    assertThat(SensitiveFields.mask("공고 01J를 찾지 못했어요")).isEqualTo("공고 01J를 찾지 못했어요");
    assertThat(SensitiveFields.mask(null)).isNull();
  }

  @Test
  void maskedExceptionsKeepTheStackButHideValuesInMessagesAndCauses() {
    var cause = new IllegalArgumentException("bad: totalAssetsWon=45000000");
    var error = new IllegalStateException("판정 실패 personalIncomeAnnualWon=32000000", cause);

    Throwable masked = SensitiveFields.masked(error);
    StringWriter trace = new StringWriter();
    masked.printStackTrace(new PrintWriter(trace));

    assertThat(trace.toString())
        .contains("java.lang.IllegalStateException: 판정 실패 personalIncomeAnnualWon=***")
        .contains("java.lang.IllegalArgumentException: bad: totalAssetsWon=***")
        .contains("SensitiveFieldsTest")
        .doesNotContain("32000000", "45000000");
  }
}
