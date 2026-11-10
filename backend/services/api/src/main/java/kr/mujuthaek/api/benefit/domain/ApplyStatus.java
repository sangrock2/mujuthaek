package kr.mujuthaek.api.benefit.domain;

import java.time.LocalDate;

/** 화면에 보여 주는 신청 상태 (공고와 같은 이름). 저장된 상태가 아니라 오늘 날짜로 계산해요. */
public enum ApplyStatus {
  UPCOMING,
  APPLYING,
  CLOSED,
  ALWAYS;

  public static ApplyStatus of(
      boolean applyAlways, LocalDate start, LocalDate end, LocalDate today) {
    if (applyAlways) return ALWAYS;
    if (start != null && today.isBefore(start)) return UPCOMING;
    if (end != null && end.isBefore(today)) return CLOSED;
    return APPLYING;
  }
}
