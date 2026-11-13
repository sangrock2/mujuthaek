"use client";

// POST /api/v1/eligibility/prepare-cost: 보증금 하나로 준비할 돈 (공고 판정의 주택형별 준비할 돈과 같은 계산)
import { useQueries } from "@tanstack/react-query";
import { useNoticeApplicant } from "@/features/notice/judgment";
import { formatWon } from "@/features/notice/format";
import { prepareNoteLabel } from "@/features/notice/labels";
import { api } from "@/shared/lib/api/client";
import { USE_MOCKS } from "@/shared/lib/api/config";
import { endpoints } from "@/shared/lib/api/endpoints";
import type { NoticeUnit } from "@/features/notice/mocks/notice";

/** 백엔드 PrepareCost.Result */
type ApiPrepareCost = {
  depositWon: number | null;
  loan: { productCode: string; name: string; amountWon: number } | null;
  prepareWon: number | null;
  /** prepareWon이 없을 때 이유 (INCOME_UNKNOWN · ASSET_UNKNOWN · PRICE_NOT_ANNOUNCED) */
  note: string | null;
};

/** 집 하나의 준비할 돈 (가격 대상이 여럿이면 대상마다) */
export type UnitPrep = { target?: string; text: string };

const noteText = (note: string | null) => prepareNoteLabel[note ?? ""] ?? "확인 필요";

const textOf = (r: ApiPrepareCost) =>
  r.prepareWon !== null ? formatWon(r.prepareWon) : noteText(r.note);

/** 계산할 보증금: 가격 대상이 여럿이면 대상마다, 아니면 집 보증금 하나 */
function depositsOf(unit: NoticeUnit) {
  return unit.prices
    ? unit.prices.map((p) => ({ target: p.target, depositWon: p.depositWon }))
    : [{ target: undefined, depositWon: unit.depositWon }];
}

/**
 * 실제 API: 고른 집의 보증금으로 준비할 돈을 다시 계산해요. 공고 판정은 주택형마다 보증금 하나로만 계산해서,
 * 같은 주택형이어도 호마다 보증금이 다른 공고(주택목록)는 고른 집 값이 달라요. 판정 입력은 공고 판정과 같아요(구간 값만).
 * 불러오는 동안은 「계산 중」, 실패하면 주택형 값(unit.prep)을 보여 줘요
 */
function useApiUnitPrep(unit: NoticeUnit | null): UnitPrep[] {
  const { ready, applicant } = useNoticeApplicant();
  const deposits = unit ? depositsOf(unit) : [];
  const results = useQueries({
    queries: deposits.map((d) => ({
      queryKey: ["notice", "prepare-cost", d.depositWon, applicant] as const,
      queryFn: () =>
        api.post<ApiPrepareCost>(endpoints.prepareCost, { applicant, depositWon: d.depositWon }),
      enabled: ready && d.depositWon != null,
      staleTime: 60 * 1000,
      gcTime: 5 * 60 * 1000,
    })),
  });
  if (!unit) return [];
  return deposits.map((d, i) => {
    const q = results[i];
    if (d.depositWon == null) return { target: d.target, text: noteText("PRICE_NOT_ANNOUNCED") };
    if (q.data) return { target: d.target, text: textOf(q.data) };
    return { target: d.target, text: q.isError ? unit.prep : "계산 중" };
  });
}

/** 목업: 주택형 값 그대로 */
function useMockUnitPrep(unit: NoticeUnit | null): UnitPrep[] {
  return unit ? [{ text: unit.prep }] : [];
}

// USE_MOCKS는 빌드 때 정해지는 값이라 훅 순서가 바뀌지 않아요
export const useUnitPrep = USE_MOCKS ? useMockUnitPrep : useApiUnitPrep;
