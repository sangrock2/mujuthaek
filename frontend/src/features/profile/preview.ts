"use client";

// 조건 입력 화면의 「지금 조건으로」: 입력 중인 조건(아직 저장 전)으로 홈 요약 API를 불러 공고·혜택 수를 바로 세어요
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { toApplicant } from "@/features/conditions/applicant";
import type { DeviceConditions, SessionConditions } from "@/features/conditions/types";
import { useCriteria } from "@/features/eligibility/criteria";
import { api } from "@/lib/api/client";
import { USE_MOCKS } from "@/lib/api/config";
import { endpoints } from "@/lib/api/endpoints";
import type { ProfilePreview } from "@/mocks/profile";

/** 입력이 이만큼 멈추면 다시 세어요 (글자마다 부르지 않게) */
const DEBOUNCE_MS = 600;

/** POST /api/v1/home/summary 응답 중 쓰는 칸 */
type Summary = {
  homes: { eligible: number; needsInput: number };
  benefits: { eligible: number };
};

/** 숫자가 없으면(받기 전·실패) null */
export type LivePreview = {
  homes: number | null;
  benefits: number | null;
  needCheck: number | null;
  /** 바뀐 조건으로 다시 세는 중 */
  updating: boolean;
  error: boolean;
};

/** 값이 ms 동안 그대로면 그 값. 처음 값(null에서 바뀔 때)은 기다리지 않아요 */
function useDebounced<T>(value: T | null, ms: number): T | null {
  const [debounced, setDebounced] = useState(value);
  if (debounced === null && value !== null) setDebounced(value); // 렌더 중 상태 맞추기
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

/**
 * @param ready 저장해 둔 조건을 다 읽었는지 (읽기 전 기본값으로 한 번 더 부르지 않게)
 * @param mock 목업 모드에서 보여 줄 예시 숫자 (단계별)
 */
export function useConditionsPreview(
  device: DeviceConditions,
  session: SessionConditions,
  ready: boolean,
  mock: ProfilePreview,
): LivePreview {
  const criteria = useCriteria();
  const body = useMemo(() => {
    const regionCodes = device.searchRegionCodes;
    return {
      filters: regionCodes.length ? { regionCodes } : {},
      applicant: toApplicant(device, session, criteria.data),
    };
  }, [device, session, criteria.data]);
  // 저장해 둔 조건을 읽기 전(기본값)에는 부르지 않아요
  const settled = useDebounced(ready && !criteria.isPending ? body : null, DEBOUNCE_MS);

  const q = useQuery({
    queryKey: ["profile", "preview", settled] as const,
    queryFn: () => api.post<Summary>(endpoints.homeSummary, settled),
    enabled: !USE_MOCKS && settled !== null,
    placeholderData: keepPreviousData, // 다시 세는 동안 앞의 숫자를 그대로 둬요
    staleTime: 60 * 1000,
    retry: false,
  });

  if (USE_MOCKS) return { ...mock, updating: false, error: false };
  return {
    homes: q.data?.homes.eligible ?? null,
    benefits: q.data?.benefits.eligible ?? null,
    needCheck: q.data?.homes.needsInput ?? null,
    updating: q.isFetching || settled !== body,
    error: q.isError,
  };
}
