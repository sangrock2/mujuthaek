package kr.mujuthaek.api.chat.domain;

/** 신고 사유. */
public enum ReportReason {
  /** 광고 */
  AD,
  /** 욕설 */
  ABUSE,
  /** 개인정보 노출 */
  PRIVACY,
  /** 허위 정보 */
  FALSE_INFO,
  /** 기타 (detail에 사유) */
  ETC
}
