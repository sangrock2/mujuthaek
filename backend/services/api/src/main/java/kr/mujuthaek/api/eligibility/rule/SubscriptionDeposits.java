package kr.mujuthaek.api.eligibility.rule;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Collection;
import java.util.Comparator;
import java.util.Optional;
import java.util.OptionalLong;

/**
 * 청약 예치기준금액 조회 (4-08 청약통장 기준, 주택공급에 관한 규칙 별표 2). 판정 코드는 이 인터페이스만 알고, 값은 service가 DB에서 읽어 줘요.
 *
 * <p>민영주택 1순위 기준이지만, 공공주택도 전용 85㎡ 초과 공공건설임대(규칙 제28조)와 장기전세(공공주택 특별법 시행규칙 제18조)는 이 기준으로 순위를 정해요.
 */
public interface SubscriptionDeposits {

  /** 기준일에 쓰는 표에서 지역·전용면적에 맞는 예치기준금액 (원). 없으면 비어 있어요. */
  OptionalLong find(LocalDate day, DepositRegion region, BigDecimal exclusiveAreaM2);

  /**
   * 표 한 칸.
   *
   * @param maxAreaM2 이 면적 이하 (null이면 모든 면적)
   */
  record Row(LocalDate effectiveFrom, DepositRegion region, BigDecimal maxAreaM2, long amountWon) {}

  /**
   * 여러 시점의 칸에서 고르기: 시행일이 기준일 이전인 가장 늦은 표를 쓰고, 그 표의 같은 지역 칸 중 면적 상한이 전용면적 이상인 가장 작은 칸, 없으면 "모든 면적"
   * 칸이에요.
   */
  static OptionalLong pick(
      Collection<Row> rows, LocalDate day, DepositRegion region, BigDecimal exclusiveAreaM2) {
    Optional<LocalDate> version =
        rows.stream()
            .map(Row::effectiveFrom)
            .filter(d -> !d.isAfter(day))
            .max(Comparator.naturalOrder());
    if (version.isEmpty()) {
      return OptionalLong.empty();
    }
    var sameTable =
        rows.stream()
            .filter(r -> r.effectiveFrom().equals(version.get()) && r.region() == region)
            .toList();
    return sameTable.stream()
        .filter(r -> r.maxAreaM2() != null && exclusiveAreaM2.compareTo(r.maxAreaM2()) <= 0)
        .min(Comparator.comparing(Row::maxAreaM2))
        .or(() -> sameTable.stream().filter(r -> r.maxAreaM2() == null).findFirst())
        .map(r -> OptionalLong.of(r.amountWon()))
        .orElse(OptionalLong.empty());
  }
}
