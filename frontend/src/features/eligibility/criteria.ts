import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { USE_MOCKS } from "@/lib/api/config";
import { endpoints } from "@/lib/api/endpoints";

/** GET /api/v1/eligibility/criteria. 금액은 원, 가구원 수("1"·"2" …)별 월액 */
export type Criteria = {
  year: number;
  validFrom: string;
  medianIncomeMonthlyWon: Record<string, number> | null;
  urbanWorkerIncomeMonthlyWon: Record<string, number> | null;
  /** 도시근로자 소득 값의 연도 (그해 값이 없으면 앞 해) */
  urbanWorkerIncomeYear: number | null;
  rankCriteria: unknown;
  /** 총자산 구간 경계 (작은 순) */
  assetCutsWon: number[];
  /** 자동차가액 구간 경계 (작은 순) */
  carCutsWon: number[];
};

/** 목업용 기준값 (실제 값은 API에서 받아요) */
export const mockCriteria: Criteria = {
  year: 2026,
  validFrom: "2026-01-01",
  medianIncomeMonthlyWon: { "1": 2564238, "2": 4199292, "3": 5359036, "4": 6494738 },
  urbanWorkerIncomeMonthlyWon: { "1": 3813363, "2": 5287584, "3": 7220405, "4": 8136513 },
  urbanWorkerIncomeYear: 2025,
  rankCriteria: null,
  assetCutsWon: [108_000_000, 245_000_000, 251_000_000, 345_000_000, 362_000_000],
  carCutsWon: [45_420_000],
};

export const criteriaKeys = { latest: ["eligibility", "criteria"] as const };

/** 판정 입력의 구간을 계산할 기준값. 하루 한 번 받아요 */
export function useCriteria() {
  return useQuery({
    queryKey: criteriaKeys.latest,
    queryFn: () =>
      USE_MOCKS ? Promise.resolve(mockCriteria) : api.get<Criteria>(endpoints.eligibilityCriteria),
    staleTime: 24 * 60 * 60 * 1000,
  });
}
