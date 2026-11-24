"use client";

import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";
import { mockQuery } from "@/features/mock-query";
import { USE_MOCKS } from "@/shared/lib/api/config";
import { safeExternalUrl } from "@/shared/lib/safeUrl";
import { formatWon } from "@/features/notice/format";
import {
  benefitsSummary,
  type Benefit,
  type BenefitCategory,
} from "@/features/benefits/mocks/benefits";
import { toBenefit, useBenefitDetailQuery, useBenefitSearch, type ApiBenefitSearch } from "./api";

export const benefitKeys = {
  summary: ["benefits", "summary"] as const,
};

export type BenefitList = {
  items: Benefit[];
  /** 분야별 개수 (지원 가능 · 확인 필요) */
  counts: Record<BenefitCategory, number>;
  total: number;
  /** "약 480만 원" · 받을 돈이 아직 없으면 "–" */
  yearlyAmount: string;
  /** "10월 26일" */
  asOf: string;
  loading: boolean;
  error: boolean;
  hasMore: boolean;
  loadMore: () => Promise<Benefit[]>;
  loadingMore: boolean;
  loadMoreError: boolean;
};

const countBy = (items: Benefit[]) => ({
  주거: items.filter((b) => b.cat === "주거").length,
  자산형성: items.filter((b) => b.cat === "자산형성").length,
  교통: items.filter((b) => b.cat === "교통").length,
});

function useMockBenefits(category?: BenefitCategory): BenefitList {
  const { data } = useQuery(mockQuery(benefitKeys.summary, benefitsSummary));
  return {
    items: category ? data.items.filter((item) => item.cat === category) : data.items,
    counts: countBy(data.items),
    total: data.items.length,
    yearlyAmount: data.yearlyAmount,
    asOf: data.asOf,
    loading: false,
    error: false,
    hasMore: false,
    loadMore: async () => [],
    loadingMore: false,
    loadMoreError: false,
  };
}

function uniqueBenefits(pages: ApiBenefitSearch[] = []) {
  const byId = new Map(pages.flatMap((page) => page.items.map((item) => [item.id, item] as const)));
  return [...byId.values()].map(toBenefit);
}

/** 실제 API: 찾아볼 지역의 혜택을 내 조건(구간 값)으로 판정해서 받아요 */
function useApiBenefits(category?: BenefitCategory): BenefitList {
  const q = useBenefitSearch(category);
  const pages = q.data?.pages;
  const first = pages?.[0];
  const items = useMemo(() => uniqueBenefits(pages), [pages]);
  const { fetchNextPage, hasNextPage, isPlaceholderData } = q;
  const hasMore = hasNextPage && !isPlaceholderData;
  const loadMore = useCallback(async () => {
    if (!hasMore) return [];
    const result = await fetchNextPage({ cancelRefetch: false });
    return uniqueBenefits(result.data?.pages);
  }, [fetchNextPage, hasMore]);
  const counts = {
    주거: first?.categoryCounts.HOUSING ?? 0,
    자산형성: first?.categoryCounts.ASSET ?? 0,
    교통: first?.categoryCounts.TRANSPORT ?? 0,
  };
  const annual = first?.summary.annualAmountWon ?? 0;
  return {
    items,
    counts,
    total: counts.주거 + counts.자산형성 + counts.교통,
    yearlyAmount: annual > 0 ? `약 ${formatWon(annual)}` : "–",
    // 날짜는 받은 뒤에만 만들어요 (미리 그리는 단계에서 new Date()를 부르지 않게)
    // 조회한 오늘을 정책 정보의 갱신 기준일처럼 표시하지 않아요.
    asOf: "",
    loading: q.isPending,
    error: q.isError && !q.data,
    hasMore,
    loadMore,
    loadingMore: q.isFetchingNextPage,
    loadMoreError: q.isFetchNextPageError,
  };
}

// USE_MOCKS는 빌드 때 정해지는 값이라 훅 순서가 바뀌지 않아요
export const useBenefits = USE_MOCKS ? useMockBenefits : useApiBenefits;

type BenefitState = { data: Benefit | undefined; loading: boolean; error: boolean };

/** 목업 단계: 없는 id면 첫 혜택을 보여줘요 */
function useMockBenefit(id: string | undefined): BenefitState {
  const { items } = useMockBenefits();
  return { data: items.find((b) => b.id === id) ?? items[0], loading: false, error: false };
}

/** 실제 API: 공개 상세 + 내 판정. 목록에서 온 값(지원 내용 한 줄)은 그대로 써요 */
function useApiBenefit(id: string | undefined, base?: Benefit): BenefitState {
  return useBenefitDetailQuery(id, base);
}

export const useBenefit: (id: string | undefined, base?: Benefit) => BenefitState = USE_MOCKS
  ? useMockBenefit
  : useApiBenefit;

/**
 * 「신청하러 가기」 주소: 신청 주소, 없으면 정책 원문. 둘 다 없으면 버튼을 숨겨요(누를 수 없는 버튼이 되지 않게).
 * http·https 주소만 써요 (data:·intent: 같은 주소는 건너뛰어요, 2026-11-16 보안 감사 L-4)
 */
export const applyHref = (b: { applyUrl?: string | null; policyUrl?: string | null }) => {
  // 시연 데이터는 주소 자리에 「#」을 둬요
  if (USE_MOCKS) return (b.applyUrl && b.applyUrl !== "#" ? b.applyUrl : b.policyUrl) || undefined;
  return safeExternalUrl(b.applyUrl) ?? safeExternalUrl(b.policyUrl) ?? undefined;
};
