package kr.mujuthaek.api.chat.domain;

/** 관리자가 신고된 메시지에 하는 일. */
public enum ReviewAction {
  /** 가림 유지 (보이던 메시지면 가려요) */
  KEEP_HIDDEN,
  /** 다시 보이게 함. 검토 전 신고 수는 0으로 돌아가요 */
  RESTORE
}
