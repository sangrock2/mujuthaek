"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { mockQuery } from "@/features/mock-query";
import { USE_MOCKS } from "@/lib/api/config";
import { formatWon } from "@/features/notice/format";
import { benefitsSummary, type Benefit, type BenefitCategory } from "@/mocks/benefits";
import { toBenefit, useBenefitDetailQuery, useBenefitSearch } from "./api";

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
  loadMore: () => void;
  loadingMore: boolean;
};

const today = () => {
  const d = new Date();
  return `${d.getMonth() + 1}월 ${d.getDate()}일`;
};

const countBy = (items: Benefit[]) => ({
  주거: items.filter((b) => b.cat === "주거").length,
  자산형성: items.filter((b) => b.cat === "자산형성").length,
  교통: items.filter((b) => b.cat === "교통").length,
});

function useMockBenefits(): BenefitList {
  const { data } = useQuery(mockQuery(benefitKeys.summary, benefitsSummary));
  return {
    items: data.items,
    counts: countBy(data.items),
    total: data.items.length,
    yearlyAmount: data.yearlyAmount,
    asOf: data.asOf,
    loading: false,
    error: false,
    hasMore: false,
    loadMore: () => {},
    loadingMore: false,
  };
}

/** 실제 API: 찾아볼 지역의 혜택을 내 조건(구간 값)으로 판정해서 받아요 */
function useApiBenefits(): BenefitList {
  const q = useBenefitSearch();
  const pages = q.data?.pages;
  const first = pages?.[0];
  const items = useMemo(() => (pages ?? []).flatMap((p) => p.items.map(toBenefit)), [pages]);
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
    asOf: first ? today() : "",
    loading: q.isPending,
    error: q.isError,
    hasMore: q.hasNextPage,
    loadMore: () => void q.fetchNextPage(),
    loadingMore: q.isFetchingNextPage,
  };
}

// USE_MOCKS는 빌드 때 정해지는 값이라 훅 순서가 바뀌지 않아요
export const useBenefits: () => BenefitList = USE_MOCKS ? useMockBenefits : useApiBenefits;

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

/** 「신청하러 가기」 주소: 신청 주소, 없으면 정책 원문. 둘 다 없으면 버튼을 숨겨요(누를 수 없는 버튼이 되지 않게) */
export const applyHref = (b: { applyUrl?: string | null; policyUrl?: string | null }) =>
  (b.applyUrl && b.applyUrl !== "#" ? b.applyUrl : b.policyUrl) || undefined;
