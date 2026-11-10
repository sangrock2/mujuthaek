package kr.mujuthaek.api.benefit;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.util.List;
import kr.mujuthaek.api.benefit.domain.ApplyStatus;
import kr.mujuthaek.api.benefit.domain.BenefitCategory;
import kr.mujuthaek.api.benefit.domain.BenefitStatus;
import org.junit.jupiter.api.Test;

class BenefitDomainTest {

  private static final LocalDate TODAY = LocalDate.of(2026, 10, 22);

  @Test
  void 상태는_범위_상시_시작전_마감_순서로_정한다() {
    assertThat(BenefitStatus.of(false, true, null, null, TODAY)).isEqualTo(BenefitStatus.HIDDEN);
    assertThat(BenefitStatus.of(true, true, null, TODAY.minusDays(1), TODAY))
        .isEqualTo(BenefitStatus.OPEN);
    assertThat(BenefitStatus.of(true, false, TODAY.plusDays(1), null, TODAY))
        .isEqualTo(BenefitStatus.UPCOMING);
    assertThat(BenefitStatus.of(true, false, null, TODAY.minusDays(1), TODAY))
        .isEqualTo(BenefitStatus.CLOSED);
    assertThat(BenefitStatus.of(true, false, null, TODAY, TODAY)).isEqualTo(BenefitStatus.OPEN);
    assertThat(ApplyStatus.of(true, null, null, TODAY)).isEqualTo(ApplyStatus.ALWAYS);
    assertThat(ApplyStatus.of(false, null, null, TODAY)).isEqualTo(ApplyStatus.APPLYING);
  }

  @Test
  void 분야는_주거_지원이_먼저이고_출처_분류로_교통_자산형성을_나눈다() {
    assertThat(BenefitCategory.of(List.of("RENT"), List.of("교통")))
        .isEqualTo(BenefitCategory.HOUSING);
    assertThat(BenefitCategory.of(List.of("CASH"), List.of("교통·이동")))
        .isEqualTo(BenefitCategory.TRANSPORT);
    assertThat(BenefitCategory.of(List.of("CASH"), List.of("금융", "자산형성")))
        .isEqualTo(BenefitCategory.ASSET);
    assertThat(BenefitCategory.of(List.of(), List.of("생활지원"))).isEqualTo(BenefitCategory.HOUSING);
  }
}
