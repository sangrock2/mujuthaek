"use client";

import { keepPreviousData, useInfiniteQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { toApplicant, type Applicant } from "@/features/conditions/applicant";
import { useConditions } from "@/features/conditions/store";
import { useCriteria } from "@/features/eligibility/criteria";
import { api } from "@/lib/api/client";
import { endpoints } from "@/lib/api/endpoints";
import type { ListingVerdict } from "@/components/ui/Badge";
import {
  noticeTypeLabel,
  prepareNoteLabel,
  providerName,
  tagLabel,
} from "@/features/notice/labels";
import type { HomeListing } from "@/mocks/homes";

/** POST /api/v1/notices/search 응답 (백엔드 NoticeSearchResponse) */
export type SearchItem = {
  id: string;
  title: string;
  provider: string | null;
  noticeType: string | null;
  regionCode: string | null;
  regionName: string | null;
  status: "UPCOMING" | "APPLYING" | "CLOSED" | "ALWAYS" | "UNKNOWN";
  applyStart: string | null;
  applyEnd: string | null;
  dday: number | null;
  overall: "ELIGIBLE" | "NEEDS_INPUT" | "INELIGIBLE";
  prepareCostWon: number | null;
  prepareCostNote: string | null;
  areaScore: number | null;
  tags: string[];
  siteCount: number;
};

export type SearchResponse = {
  counts: { eligible: number; needsInput: number; ineligible: number };
  items: SearchItem[];
  nextCursor: string | null;
  hasNext: boolean;
};

export type SearchSort = "RECOMMENDED" | "DEADLINE" | "PREPARE_COST" | "AREA_SCORE";

export type SearchFilters = {
  /** 찾아볼 지역 (시·도 2자리 · 시·군·구 5자리). 비우면 전체 */
  regionCodes: string[];
  tenure: "RENT" | "BUY";
  /** 공고 유형 코드 (비우면 전부) */
  noticeTypes?: string[];
  includeIneligible: boolean;
  sort: SearchSort;
};

const PAGE_SIZE = 20;

const verdictOf: Record<SearchItem["overall"], ListingVerdict> = {
  ELIGIBLE: "ok",
  NEEDS_INPUT: "check",
  INELIGIBLE: "no",
};

/** 1,234,567원 → "124만 원" (만 원 아래 올림) */
export function manWonLabel(won: number) {
  const man = Math.ceil(won / 10_000);
  return `${man.toLocaleString("ko-KR")}만 원`;
}

function dueOf(item: SearchItem) {
  if (item.status === "ALWAYS") return "상시";
  if (item.status === "UPCOMING") return "접수 예정";
  if (item.dday === null) return "마감일 확인";
  return item.dday <= 0 ? "오늘 마감" : `D-${item.dday}`;
}

/** 응답 한 줄 → 목록 카드 */
export function toListing(item: SearchItem): HomeListing {
  const org = [
    providerName(item.provider),
    item.noticeType ? noticeTypeLabel[item.noticeType] : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return {
    id: item.id,
    verdict: verdictOf[item.overall],
    org,
    title: item.title,
    // 목록 응답에는 아직 보증금·월세가 없어요 (공고 상세에서 보여요)
    price: "",
    tags: item.tags.map((t) => tagLabel[t]).filter(Boolean),
    life:
      item.areaScore === null
        ? undefined
        : `생활권 ${item.siteCount > 1 ? "최고 " : ""}${Math.round(item.areaScore)}점`,
    prepAmount: item.prepareCostWon !== null ? manWonLabel(item.prepareCostWon) : undefined,
    prepNote:
      item.prepareCostWon === null
        ? (prepareNoteLabel[item.prepareCostNote ?? ""] ?? "준비할 돈 확인 필요")
        : undefined,
    due: dueOf(item),
    region: item.regionCode ?? "nationwide",
    regionName: item.regionName ?? undefined,
    liked: false,
  };
}

/**
 * 내 조건 맞춤 목록. 조건은 구간 값으로만 보내고(정확한 소득·자산은 브라우저에만),
 * 지역 거르기 · 판정 · 커서 페이지는 서버가 해요. 응답은 캐시하지 않는 값이라 쿼리 키에도 구간만 넣어요
 */
export function useNoticeSearch(filters: SearchFilters, enabled = true) {
  const stored = useConditions();
  const criteria = useCriteria();
  const ready = stored.status === "ready" && !criteria.isPending;
  const applicant: Applicant = useMemo(
    () =>
      stored.status === "ready" ? toApplicant(stored.device, stored.session, criteria.data) : {},
    [stored, criteria.data],
  );

  return useInfiniteQuery({
    queryKey: ["notices", "search", filters, applicant] as const,
    queryFn: ({ pageParam }) =>
      api.post<SearchResponse>(endpoints.noticesSearch, {
        filters: {
          regionCodes: filters.regionCodes.length ? filters.regionCodes : undefined,
          tenure: filters.tenure,
          noticeTypes: filters.noticeTypes?.length ? filters.noticeTypes : undefined,
        },
        applicant,
        sort: filters.sort,
        includeIneligible: filters.includeIneligible,
        cursor: pageParam,
        size: PAGE_SIZE,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => (last.hasNext ? last.nextCursor : null),
    enabled: enabled && ready,
    // 조건으로 계산한 결과라 오래 두지 않아요 (지역·조건을 바꾸면 새로 받아요)
    staleTime: 60 * 1000,
    gcTime: 5 * 60 * 1000,
    placeholderData: keepPreviousData,
  });
}
