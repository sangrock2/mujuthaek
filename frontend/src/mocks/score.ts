// 화면용 예시 데이터 (디자인 WebScore · MScore). 실제 값은 API에서 받아요.

export type ScoreProfile = {
  /** 내 조건으로 미리 채운 선택지 순서 (무주택 기간 · 부양가족 수 · 청약통장 가입 기간) */
  prefill: { homeless: number; dependents: number; account: number };
  /** 무주택 기간 설명 뒤에 붙는 내 상황 (PC) */
  homelessNote: string;
  /** 비교 예시: 최근 당첨 최저 가점 */
  cutoff: { label: string; score: number };
};

export const scoreProfile: ScoreProfile = {
  prefill: { homeless: 0, dependents: 0, account: 3 },
  homelessNote: "지금 만 29세 미혼이라 0점이에요.",
  cutoff: { label: "○○ 민영 아파트 최근 당첨 최저 가점", score: 54 },
};
