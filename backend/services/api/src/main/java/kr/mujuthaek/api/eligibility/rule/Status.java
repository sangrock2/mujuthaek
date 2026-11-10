package kr.mujuthaek.api.eligibility.rule;

import java.util.Collection;

/** 조건 하나의 판정: MET 충족 · NOT_MET 불충족 · UNKNOWN 확인 필요 (입력 없음, 검수 중, 판정할 수 없는 조건). */
public enum Status {
  MET,
  NOT_MET,
  UNKNOWN;

  /** 모두 만족해야 할 때: 하나라도 불충족이면 불충족, 모두 충족이면 충족, 그 밖은 확인 필요. */
  public static Status all(Collection<Status> statuses) {
    if (statuses.contains(NOT_MET)) {
      return NOT_MET;
    }
    return statuses.stream().allMatch(s -> s == MET) ? MET : UNKNOWN;
  }

  /** 하나만 만족하면 될 때: 하나라도 충족이면 충족, 모두 불충족이면 불충족, 그 밖은 확인 필요. */
  public static Status any(Collection<Status> statuses) {
    if (statuses.contains(MET)) {
      return MET;
    }
    return !statuses.isEmpty() && statuses.stream().allMatch(s -> s == NOT_MET) ? NOT_MET : UNKNOWN;
  }
}
