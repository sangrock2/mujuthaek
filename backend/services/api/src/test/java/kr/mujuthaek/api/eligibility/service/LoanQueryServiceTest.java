package kr.mujuthaek.api.eligibility.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.LocalDate;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.eligibility.dto.request.JudgmentApplicantRequest;
import kr.mujuthaek.api.eligibility.model.LoanResult;
import kr.mujuthaek.api.eligibility.model.MissingInput;
import kr.mujuthaek.api.eligibility.rule.Eligibility;
import kr.mujuthaek.api.eligibility.rule.loan.LoanType;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.context.annotation.Import;
import tools.jackson.databind.json.JsonMapper;

/**
 * 대출 자격 판정 서비스를 실제 스프링·DB(Testcontainers, 대출 상품 마이그레이션)로 불러요. 입력 → 상품별 결과·이유 → 정렬된 결과, 오류 코드, 로그까지
 * 봐요.
 */
@SpringBootTest
@Import(TestcontainersConfiguration.class)
@ExtendWith(OutputCaptureExtension.class)
class LoanQueryServiceTest {

  private static final JsonMapper JSON = JsonMapper.builder().build();
  private static final LocalDate AS_OF = LocalDate.parse("2026-10-21");

  @Autowired private LoanQueryService loans;

  private LoanResult judge(String applicant) {
    return loans.judge(JSON.readValue(applicant, JudgmentApplicantRequest.class), AS_OF);
  }

  private static LoanResult.Item product(LoanResult result, String code) {
    return result.items().stream()
        .filter(i -> i.productCode().equals(code))
        .findFirst()
        .orElseThrow();
  }

  // 만 27세 미혼 1인 세대, 무주택, 연소득 4천만 원, 순자산 1억 원, 자녀 없음, 생애최초
  private static final String YOUTH =
      """
      {"birthDate": "1999-05-05", "maritalStatus": "SINGLE", "childBirthDates": [],
       "household": {"size": 1, "homeless": true},
       "loan": {"annualIncomeWon": 40000000, "applicantAnnualIncomeWon": 40000000,
                "netAssetWon": 100000000, "firstHomePurchase": true}}""";

  @Test
  void judgesEveryProductWithReasons() {
    LoanResult result = judge(YOUTH);

    assertThat(result.asOf()).isEqualTo(AS_OF);
    assertThat(result.items()).hasSize(10);
    assertThat(result.counts()).isEqualTo(new LoanResult.Counts(4, 1, 5));
    // 지원 가능이 먼저, 같은 상태끼리는 전세 → 월세 → 구입
    assertThat(result.items().get(0).productCode()).isEqualTo("BEOTIMMOK_GENERAL");
    assertThat(result.items().get(0).loanType()).isEqualTo(LoanType.JEONSE);
    LoanResult.Item youth = result.items().get(1);
    assertThat(youth.productCode()).isEqualTo("BEOTIMMOK_YOUTH");
    assertThat(youth.status()).isEqualTo(Eligibility.ELIGIBLE);
    assertThat(youth.failedConditions()).isEmpty();
    assertThat(youth.limitSummary()).contains("1.5억 원");
    assertThat(youth.rateSummary()).isEqualTo("연 2.2~3.3%");
    assertThat(youth.sourceUrl())
        .isEqualTo("https://nhuf.molit.go.kr/FP/FP05/FP0502/FP05020301.jsp");
    // 확인 필요: 청년 주택드림 (청약 당첨은 입력으로 알 수 없어요)
    LoanResult.Item dream = result.items().get(4);
    assertThat(dream.productCode()).isEqualTo("DIDIMDOL_YOUTH_DREAM");
    assertThat(dream.status()).isEqualTo(Eligibility.NEEDS_INPUT);
    assertThat(dream.checkReasons().getFirst()).contains("청년 주택드림 통장");
    // 불가: 이유가 있고, 넣을 입력은 보여 주지 않아요
    LoanResult.Item newlywed = result.items().get(5);
    assertThat(newlywed.productCode()).isEqualTo("BEOTIMMOK_NEWLYWED");
    assertThat(newlywed.status()).isEqualTo(Eligibility.INELIGIBLE);
    assertThat(newlywed.failedConditions().getFirst())
        .isEqualTo("혼인 7년 이내 신혼부부(또는 3개월 안 결혼 예정)여야 해요");
    assertThat(newlywed.missingInputs()).isEmpty();
    LoanResult.Item didimdol = product(result, "DIDIMDOL");
    assertThat(didimdol.status()).isEqualTo(Eligibility.INELIGIBLE);
    assertThat(didimdol.failedConditions().getFirst()).isEqualTo("만 30세 미만 미혼 단독세대주는 받을 수 없어요");
  }

  @Test
  void missingInputsTellWhatToAsk() {
    LoanResult result = judge("{\"birthDate\": \"1999-05-05\"}");

    assertThat(result.counts().eligible()).isZero();
    assertThat(product(result, "BEOTIMMOK_YOUTH").missingInputs())
        .extracting(MissingInput::field)
        .contains("loan.annualIncomeWon");
    assertThat(product(result, "BEOTIMMOK_YOUTH").missingInputs())
        .extracting(MissingInput::label)
        .contains("부부합산 순자산");
    assertThat(product(result, "DIDIMDOL_NEWLYWED").missingInputs())
        .extracting(MissingInput::field)
        .contains("loan.firstHomePurchase");
  }

  @Test
  void applicantAndDayAreOptional() {
    LoanResult result = loans.judge(null, null);

    assertThat(result.asOf()).isNotNull();
    assertThat(result.items()).hasSize(10);
    assertThat(result.items())
        .extracting(LoanResult.Item::status)
        .doesNotContain(Eligibility.ELIGIBLE);
  }

  @Test
  void rejectsBrokenMoneyWithoutEchoingIt() {
    assertThatThrownBy(() -> judge("{\"loan\": {\"annualIncomeWon\": -7654321}}"))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.VALIDATION_FAILED))
        .hasMessageNotContaining("7654321");
    assertThatThrownBy(
            () ->
                judge(
                    "{\"loan\": {\"annualIncomeWon\": 30000000, \"applicantAnnualIncomeWon\": 40000000}}"))
        .isInstanceOf(CustomException.class);
  }

  @Test
  void personalInputsNeverReachTheLogs(CapturedOutput output) {
    String applicant =
        """
        {"birthDate": "1987-06-05", "household": {"homeless": true},
         "loan": {"annualIncomeWon": 43218765, "netAssetWon": 198765432}}""";
    LoanResult result = judge(applicant);
    assertThat(JSON.writeValueAsString(result))
        .doesNotContain("43218765")
        .doesNotContain("198765432");
    assertThatThrownBy(() -> judge(applicant.replace("43218765", "-43218765")))
        .isInstanceOf(CustomException.class);
    assertThat(output.getAll())
        .doesNotContain("43218765")
        .doesNotContain("4,321")
        .doesNotContain("198765432")
        .doesNotContain("1987-06-05");
  }
}
