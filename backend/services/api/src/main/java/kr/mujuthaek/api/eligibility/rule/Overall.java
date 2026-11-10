package kr.mujuthaek.api.eligibility.rule;

import java.util.Collection;

/** 공급 대상·공고의 판정: ELIGIBLE 지원 가능 · NEEDS_INPUT 확인 필요 · INELIGIBLE 지원 불가. */
public enum Overall {
  ELIGIBLE,
  NEEDS_INPUT,
  INELIGIBLE;

  /** 공급 대상 하나: 조건이 모두 충족이면 지원 가능, 불충족이 하나라도 있으면 지원 불가, 그 밖은 확인 필요. */
  public static Overall of(Status allConditions) {
    return switch (allConditions) {
      case MET -> ELIGIBLE;
      case NOT_MET -> INELIGIBLE;
      case UNKNOWN -> NEEDS_INPUT;
    };
  }

  /** 공고 전체: 대상 하나라도 지원 가능이면 지원 가능, 아니면 확인 필요가 있으면 확인 필요, 그 밖은 지원 불가. */
  public static Overall best(Collection<Overall> targets) {
    if (targets.contains(ELIGIBLE)) {
      return ELIGIBLE;
    }
    return targets.contains(NEEDS_INPUT) ? NEEDS_INPUT : INELIGIBLE;
  }
}
