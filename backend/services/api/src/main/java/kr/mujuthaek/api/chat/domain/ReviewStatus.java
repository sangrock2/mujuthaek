package kr.mujuthaek.api.chat.domain;

/** 신고 검토 상태. */
public enum ReviewStatus {
  /** 관리자 검토 전 */
  PENDING,
  /** 관리자가 가림을 유지함 */
  KEPT_HIDDEN,
  /** 관리자가 다시 보이게 함 */
  RESTORED
}
