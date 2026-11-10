package kr.mujuthaek.api.eligibility.rule;

/** 판정 분야. 분야마다 판정 틀(JSON 형식)과 판정 서비스 메서드가 따로 있어요. */
public enum Field {
  /** 주거 (housing-judgment.v1). */
  HOUSING,
  /** 창업지원 (startup-support-judgment.v1). */
  STARTUP_SUPPORT,
  /** 사업공간 (business-space-judgment.v1). */
  BUSINESS_SPACE
}
