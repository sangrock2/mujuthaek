package kr.mujuthaek.api.eligibility.rule;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.LocalDate;
import kr.mujuthaek.api.eligibility.MigrationDeposits;
import org.junit.jupiter.api.Test;

/** 청약 예치기준금액 (주택공급에 관한 규칙 별표 2): 지역 열 고르기와 면적 칸 고르기. 값은 마이그레이션에 넣은 그대로예요. */
class SubscriptionDepositsTest {

  private static final LocalDate DAY = LocalDate.of(2026, 10, 16);
  private static final MigrationDeposits TABLE = MigrationDeposits.load();

  private static long amount(DepositRegion region, String area) {
    return TABLE.find(DAY, region, new BigDecimal(area)).orElseThrow();
  }

  @Test
  void theTableHasTwelveCells() {
    assertThat(TABLE.rows()).hasSize(12);
  }

  @Test
  void theAreaPicksTheSmallestBandThatFits() {
    assertThat(amount(DepositRegion.SEOUL_BUSAN, "59")).isEqualTo(3_000_000);
    assertThat(amount(DepositRegion.SEOUL_BUSAN, "85")).as("85㎡ 이하에 85㎡ 포함").isEqualTo(3_000_000);
    assertThat(amount(DepositRegion.SEOUL_BUSAN, "85.01")).isEqualTo(6_000_000);
    assertThat(amount(DepositRegion.SEOUL_BUSAN, "114.92")).isEqualTo(10_000_000);
    assertThat(amount(DepositRegion.SEOUL_BUSAN, "135.5")).as("모든 면적").isEqualTo(15_000_000);
    assertThat(amount(DepositRegion.METROPOLITAN, "114.92")).isEqualTo(7_000_000);
    assertThat(amount(DepositRegion.OTHER, "114.92")).isEqualTo(4_000_000);
    assertThat(amount(DepositRegion.OTHER, "200")).isEqualTo(5_000_000);
  }

  @Test
  void beforeTheTableTookEffectThereIsNoAmount() {
    assertThat(TABLE.find(LocalDate.of(2019, 10, 31), DepositRegion.OTHER, BigDecimal.TEN))
        .isEmpty();
  }

  @Test
  void theRegionColumnFollowsTheApplicantsSido() {
    assertThat(DepositRegion.of("1165000000", DAY)).hasValue(DepositRegion.SEOUL_BUSAN);
    assertThat(DepositRegion.of("26", DAY)).hasValue(DepositRegion.SEOUL_BUSAN);
    assertThat(DepositRegion.of("2823700000", DAY)).hasValue(DepositRegion.METROPOLITAN);
    assertThat(DepositRegion.of("4113500000", DAY)).hasValue(DepositRegion.OTHER);
    assertThat(DepositRegion.of("36110", DAY)).as("세종특별자치시").hasValue(DepositRegion.OTHER);
    assertThat(DepositRegion.of("99", DAY)).as("모르는 시도").isEmpty();
  }

  @Test
  void gwangjuAndJeonnamAreUndecidedAfterTheMerger() {
    LocalDate before = DepositRegion.GWANGJU_JEONNAM_MERGED.minusDays(1);
    assertThat(DepositRegion.of("29", before)).hasValue(DepositRegion.METROPOLITAN);
    assertThat(DepositRegion.of("46", before)).hasValue(DepositRegion.OTHER);
    assertThat(DepositRegion.of("29", DAY)).isEmpty();
    assertThat(DepositRegion.of("46", DAY)).isEmpty();
  }
}
