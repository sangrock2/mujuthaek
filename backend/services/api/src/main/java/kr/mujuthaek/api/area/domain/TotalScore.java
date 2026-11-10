package kr.mujuthaek.api.area.domain;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Map;

/**
 * 요청 때 계산하는 생활권 총점(저장 안 함). 총점 = Σ(항목 점수 × 가중치) ÷ 가중치 합, 0~100 정수.
 *
 * <p>점수가 있는 항목만 셈해요(직장을 안 넣으면 {@link LifeCategory#WORK}는 빠짐). 그 항목들의 가중치가 모두 0이면 같은 비중이에요. 반올림은 0.5
 * 올림({@link RoundingMode#HALF_UP})으로 SQL {@code round()}와 같게 해요 — {@code BigDecimal} 기본처럼 {@code
 * HALF_EVEN}이면 76.5가 76이 되어 SQL(77)과 달라져요.
 */
public final class TotalScore {

  private TotalScore() {}

  /**
   * @param scores 항목 점수 0~100 (직장은 거리 규칙 결과라 소수일 수 있음)
   * @param weights 사용자 가중치 0~10. 없는 항목은 0
   */
  public static int of(Map<LifeCategory, BigDecimal> scores, Map<LifeCategory, Integer> weights) {
    if (scores.isEmpty()) {
      throw new IllegalArgumentException("점수가 있는 항목이 없어요");
    }
    BigDecimal weightSum = BigDecimal.ZERO;
    for (LifeCategory c : scores.keySet()) {
      weightSum = weightSum.add(BigDecimal.valueOf(weight(weights, c)));
    }
    boolean equal = weightSum.signum() == 0;
    BigDecimal sum = BigDecimal.ZERO;
    for (Map.Entry<LifeCategory, BigDecimal> e : scores.entrySet()) {
      BigDecimal w = equal ? BigDecimal.ONE : BigDecimal.valueOf(weight(weights, e.getKey()));
      sum = sum.add(e.getValue().multiply(w));
    }
    BigDecimal divisor = equal ? BigDecimal.valueOf(scores.size()) : weightSum;
    return sum.divide(divisor, 0, RoundingMode.HALF_UP).intValueExact();
  }

  private static int weight(Map<LifeCategory, Integer> weights, LifeCategory c) {
    int w = weights.getOrDefault(c, 0);
    if (w < 0) {
      throw new IllegalArgumentException("가중치는 0 이상이어야 해요: " + c);
    }
    return w;
  }
}
