package kr.mujuthaek.api.notice.domain;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;

/**
 * 접수 상태 (API 설계 "이번에 정하는 코드"). 원문 일정으로 계산해 저장하고, 상태가 바뀔 수 있는 시각에 다시 계산해요 ({@link
 * ApplicationStatusCalculator}).
 */
public enum NoticeStatus {
  /** 접수예정: 다음 접수 기간이 아직 오지 않음 */
  UPCOMING,
  /** 접수중 */
  APPLYING,
  /** 마감: 모든 접수 기간이 끝남 */
  CLOSED,
  /** 상시: 원문에 상시 모집이 명시됨 */
  ALWAYS,
  /** 확인 필요: 일정이 없거나 확실하지 않아 단정할 수 없음 */
  UNKNOWN;

  /** 마감까지 남은 날 (마감일 당일 0). 마감일이 없거나 지났으면 null. */
  public static Integer dday(LocalDate applyEnd, LocalDate today) {
    if (applyEnd == null || today.isAfter(applyEnd)) {
      return null;
    }
    return (int) ChronoUnit.DAYS.between(today, applyEnd);
  }
}
