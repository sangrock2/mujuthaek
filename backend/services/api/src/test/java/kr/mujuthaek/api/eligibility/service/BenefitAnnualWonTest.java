package kr.mujuthaek.api.eligibility.service;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.benefit.service.BenefitForJudgment;
import kr.mujuthaek.api.benefit.service.BenefitForJudgment.Support;
import org.junit.jupiter.api.Test;

/** 혜택의 1년에 받을 수 있는 돈 (목록 순서·합계에 써요). */
class BenefitAnnualWonTest {

  private static BenefitForJudgment benefit(Support... supports) {
    return new BenefitForJudgment(
        UUID.randomUUID(),
        "혜택",
        "기관",
        "HOUSING",
        null,
        "NATIONWIDE",
        List.of(),
        List.of(),
        null,
        null,
        true,
        false,
        List.of(supports),
        List.of(),
        java.time.Instant.EPOCH);
  }

  private static Support support(String kind, Long won, String per, Integer months, String raw) {
    return new Support(kind, won, per, months, null, raw);
  }

  @Test
  void 연차별_월_지원은_더하지_않고_가장_큰_해만_1년치() {
    // 청년 어촌 정착 지원: 예전엔 (110 + 100 + 90)만 × 12 = 3,600만 원
    var b =
        benefit(
            support("MOVE_IN_GRANT", 1_100_000L, "MONTH", null, "1년차 월 110만원"),
            support("MOVE_IN_GRANT", 1_000_000L, "MONTH", null, "2년차 월 100만원"),
            support("MOVE_IN_GRANT", 900_000L, "MONTH", null, "3년차 월 90만원"));
    assertThat(BenefitEvaluationService.annualWon(b)).isEqualTo(13_200_000L);
  }

  @Test
  void 유형별_금액이나_중복도_가장_큰_것만() {
    // 무주택 노인 주거비: 가형·나형·다형 중 하나만 받아요
    var types =
        benefit(
            support("RENT", 400_000L, "ONCE", null, "가형"),
            support("RENT", 600_000L, "ONCE", null, "나형"),
            support("RENT", 700_000L, "ONCE", null, "다형"));
    assertThat(BenefitEvaluationService.annualWon(types)).isEqualTo(700_000L);
    // 같은 월세 지원이 두 줄로 들어온 경우
    var duplicated =
        benefit(
            support("RENT", 200_000L, "MONTH", null, "월세 20만 원 지원"),
            support("RENT", 200_000L, "MONTH", 12, "월임차료 최대 20만 원, 최대 12개월"));
    assertThat(BenefitEvaluationService.annualWon(duplicated)).isEqualTo(2_400_000L);
  }

  @Test
  void 다른_종류끼리는_더하고_대출과_금액_없는_지원은_빼요() {
    var b =
        benefit(
            support("RENT", 200_000L, "MONTH", 6, "월 20만 원, 6개월"),
            support("MOVE_IN_GRANT", 1_000_000L, "ONCE", null, "이사비 100만 원"),
            support("DEPOSIT_LOAN", 50_000_000L, "ONCE", null, "보증금 대출 5천만 원"),
            support("CASH", null, null, null, "생계비"));
    assertThat(BenefitEvaluationService.annualWon(b)).isEqualTo(2_200_000L);
  }
}
