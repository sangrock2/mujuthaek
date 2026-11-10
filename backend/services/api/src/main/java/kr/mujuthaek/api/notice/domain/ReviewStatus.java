package kr.mujuthaek.api.notice.domain;

/** extraction.completed의 reviewStatus. 추출 결과를 자동 검증·검수한 상태예요. */
public enum ReviewStatus {
  /** 자동 검증을 모두 통과 */
  AUTO_PASSED,
  /** 공고는 믿을 만하고 일부 항목만 보류 (heldItems) */
  PARTIALLY_PASSED,
  /** 사람 검수 대기 */
  IN_REVIEW,
  /** 사람이 검수해 승인 */
  APPROVED;

  /** 사용자에게 공개할 수 있는 결과인지. */
  public boolean publishable() {
    return this != IN_REVIEW;
  }
}
