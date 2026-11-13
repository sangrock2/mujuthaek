// 화면용 예시 데이터 (디자인 WebScore · MScore). 실제 점수는 API(POST /eligibility/subscription-score)에서 받아요.
import type { ScoreInput } from "@/features/score/score";

export type ScoreProfile = {
  /** 저장한 조건이 없을 때 목업 모드에서 미리 채우는 예시 입력 */
  example: ScoreInput;
  /** 비교 예시: 최근 당첨 최저 가점 */
  cutoff: { label: string; score: number };
};

export const scoreProfile: ScoreProfile = {
  example: {
    birthDate: "1997-03-15",
    marital: "SINGLE",
    homeOwner: false,
    homelessSince: "1997-03",
    dependents: 0,
    joinedOn: "2023-05",
  },
  cutoff: { label: "○○ 민영 아파트 최근 당첨 최저 가점", score: 54 },
};
