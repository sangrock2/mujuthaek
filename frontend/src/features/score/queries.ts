import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { mockQuery } from "@/features/mock-query";
import { calculateScore, type Score, type ScoreInput } from "@/features/score/score";
import { api } from "@/lib/api/client";
import { USE_MOCKS } from "@/lib/api/config";
import { endpoints } from "@/lib/api/endpoints";
import { scoreProfile } from "@/mocks/score";

export const scoreKeys = {
  profile: ["score", "profile"] as const,
  calc: (input: ScoreInput) => ["score", "calc", input] as const,
};

export function useScoreProfile() {
  return useQuery(mockQuery(scoreKeys.profile, scoreProfile));
}

/** 입력을 멈추고 이 시간이 지나면 서버에 물어요 (글자마다 부르지 않게) */
const DEBOUNCE_MS = 400;

function useDebounced<T>(value: T, ms: number) {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return settled;
}

/** POST 본문 applicant (백엔드 ScoreApplicantRequest). 빈 칸은 보내지 않아요 */
const toApplicant = (a: ScoreInput) => ({
  birthDate: a.birthDate,
  marital: a.marital,
  marriedOn: a.marriedOn,
  homelessSince: a.homelessSince,
  homeOwner: a.homeOwner,
  dependents: a.dependents,
  subscription: a.joinedOn ? { joinedOn: a.joinedOn } : undefined,
});

export type ScoreState = {
  score: Score | null;
  /** 바꾼 값으로 다시 계산하는 중 (앞 점수를 그대로 보여 줘요) */
  updating: boolean;
  error: boolean;
};

/**
 * 실제 API: 백엔드가 기준이에요. 입력이 멈추면(400ms) 한 번 불러요. 입력에 생년월일 등이 있어서 저장하지 않고
 * 메모리에만 잠깐 둬요 (서버도 저장·캐시하지 않아요)
 */
function useApiScore(input: ScoreInput | null): ScoreState {
  const settled = useDebounced(input, DEBOUNCE_MS);
  const q = useQuery({
    queryKey: scoreKeys.calc(settled ?? {}),
    queryFn: () =>
      api.post<Score>(endpoints.subscriptionScore, { applicant: toApplicant(settled!) }),
    enabled: settled !== null,
    placeholderData: keepPreviousData,
    staleTime: 60 * 1000,
    gcTime: 60 * 1000,
    retry: false,
  });
  return {
    score: q.data ?? null,
    updating: input !== settled || q.isFetching,
    error: q.isError && !q.isFetching,
  };
}

/** 목업: 같은 규칙을 화면에서 바로 계산해요 */
function useMockScore(input: ScoreInput | null, today: string | null): ScoreState {
  return {
    score: input && today ? calculateScore(input, today) : null,
    updating: false,
    error: false,
  };
}

// USE_MOCKS는 빌드 때 정해지는 값이라 훅 순서가 바뀌지 않아요
export const useScore: (input: ScoreInput | null, today: string | null) => ScoreState = USE_MOCKS
  ? useMockScore
  : useApiScore;
