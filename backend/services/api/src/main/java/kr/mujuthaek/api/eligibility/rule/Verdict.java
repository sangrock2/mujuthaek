package kr.mujuthaek.api.eligibility.rule;

import java.util.Collection;

/** 조건 하나(또는 대상군 하나)의 판정. 확인 필요는 사용자가 값을 넣지 않았거나 기준값이 없어서 판단할 수 없을 때예요. */
public enum Verdict {
  MET,
  NOT_MET,
  UNKNOWN;

  /** 모두 충족해야 할 때 (한 대상군의 조건들): 하나라도 불충족이면 불충족, 그다음 확인 필요, 나머지는 충족. */
  public static Verdict all(Collection<Verdict> verdicts) {
    if (verdicts.contains(NOT_MET)) {
      return NOT_MET;
    }
    return verdicts.contains(UNKNOWN) ? UNKNOWN : MET;
  }

  /** 하나만 충족하면 될 때 (여러 길 중 하나, 대상군끼리): 하나라도 충족이면 충족, 그다음 확인 필요, 나머지는 불충족. */
  public static Verdict any(Collection<Verdict> verdicts) {
    if (verdicts.contains(MET)) {
      return MET;
    }
    return verdicts.contains(UNKNOWN) ? UNKNOWN : NOT_MET;
  }

  /** 참·거짓 비교 결과를 판정으로. 값이 없으면 확인 필요. */
  public static Verdict of(Boolean met) {
    if (met == null) {
      return UNKNOWN;
    }
    return met ? MET : NOT_MET;
  }
}
