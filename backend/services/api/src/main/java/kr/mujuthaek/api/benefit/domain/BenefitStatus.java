package kr.mujuthaek.api.benefit.domain;

import java.time.LocalDate;

/**
 * 혜택 상태 (policy-extracted.draft.md 4장 "상태 계산"). 위에서부터 먼저 맞는 것을 써요: 범위 밖이면 HIDDEN, 상시면 OPEN, 시작 전이면
 * UPCOMING, 마감이 지났으면 CLOSED, 그 밖은 OPEN.
 */
public enum BenefitStatus {
  UPCOMING,
  OPEN,
  CLOSED,
  HIDDEN;

  public static BenefitStatus of(
      boolean relevant, boolean applyAlways, LocalDate start, LocalDate end, LocalDate today) {
    if (!relevant) return HIDDEN;
    if (applyAlways) return OPEN;
    if (start != null && today.isBefore(start)) return UPCOMING;
    if (end != null && end.isBefore(today)) return CLOSED;
    return OPEN;
  }
}
