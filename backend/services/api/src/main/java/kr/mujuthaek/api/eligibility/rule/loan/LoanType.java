package kr.mujuthaek.api.eligibility.rule.loan;

/** 대출 구분: 무엇에 쓰는 돈인지. */
public enum LoanType {
  /** 전세 보증금. */
  JEONSE,
  /** 월세 보증금·월세. */
  MONTHLY_RENT,
  /** 집 구입 (분양·매매). */
  PURCHASE
}
