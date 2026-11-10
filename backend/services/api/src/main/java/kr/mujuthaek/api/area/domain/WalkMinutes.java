package kr.mujuthaek.api.area.domain;

import java.math.BigDecimal;
import java.math.RoundingMode;

/**
 * 직선거리로 어림한 도보 분. 저장하지 않고 화면에 줄 때 계산해요.
 *
 * <p>직선거리 × 1.3(길이 돌아가는 만큼) ÷ 분당 67m, 올림. 소수 오차로 13분이 14분이 되지 않게 {@link BigDecimal}로 셈해요.
 */
public final class WalkMinutes {

  private static final BigDecimal DETOUR_TENTHS = BigDecimal.valueOf(13);
  private static final BigDecimal METERS_PER_MINUTE_TENTHS = BigDecimal.valueOf(670);

  private WalkMinutes() {}

  public static int of(BigDecimal straightMeters) {
    if (straightMeters.signum() < 0) {
      throw new IllegalArgumentException("거리는 0 이상이어야 해요");
    }
    return straightMeters
        .multiply(DETOUR_TENTHS)
        .divide(METERS_PER_MINUTE_TENTHS, 0, RoundingMode.CEILING)
        .intValueExact();
  }
}
