"use client";

import { USE_MOCKS } from "@/lib/api/config";
import type { HomeListing } from "@/mocks/homes";
import { sortParam, tenureParam, type MoveInMode, type SortOption } from "./filters";
import { useHomes } from "./queries";
import type { RegionFilter } from "./region";
import { toListing, useNoticeSearch } from "./search";

export type HomeListState = {
  region: RegionFilter;
  mode: MoveInMode;
  sort: SortOption;
  /** 지원 불가 공고까지 보기 */
  includeIneligible: boolean;
  /** 공고 유형 코드로 거르기 (없으면 전부, filters.noticeTypesOf) */
  noticeTypes?: string[];
  /** 판정으로 거르기 (지원 가능 · 확인 필요 체크) */
  showOk: boolean;
  showCheck: boolean;
};

export type HomeList = {
  listings: HomeListing[];
  /** "지원할 수 있는 곳 N곳" */
  eligibleCount: number;
  /** 확인 필요 · 지원 불가 개수 (API일 때만) */
  needsInputCount: number | null;
  ineligibleCount: number | null;
  /** 더 보기 버튼 문구에 쓰는 남은 수. 모르면 null */
  remaining: number | null;
  hasMore: boolean;
  loadMore: () => void;
  loading: boolean;
  loadingMore: boolean;
  error: boolean;
};

const byVerdict = (s: HomeListState) => (l: HomeListing) =>
  (l.verdict !== "ok" || s.showOk) && (l.verdict !== "check" || s.showCheck);

/** 목업: 받은 첫 페이지를 지역으로 걸러요 (판정은 목업 값) */
function useMockList(s: HomeListState): HomeList {
  const { data } = useHomes();
  const visible = data.listings.filter(s.region.matches).filter(byVerdict(s));
  const count = s.region.isAll ? data.total : visible.length;
  const remaining = s.region.isAll ? data.total - data.listings.length : 0;
  return {
    listings: visible,
    eligibleCount: count,
    needsInputCount: null,
    ineligibleCount: null,
    remaining,
    hasMore: remaining > 0,
    loadMore: () => {},
    loading: false,
    loadingMore: false,
    error: false,
  };
}

/** 실제 API: 지역 거르기 · 판정 · 커서는 서버가 해요 */
function useApiList(s: HomeListState): HomeList {
  const q = useNoticeSearch({
    regionCodes: s.region.codes,
    tenure: tenureParam[s.mode],
    // 유형은 빌려서 들어가기의 임대 유형이라 사서 들어가기에는 보내지 않아요
    noticeTypes: s.mode === "빌려서 들어가기" ? s.noticeTypes : undefined,
    includeIneligible: s.includeIneligible,
    sort: sortParam[s.sort],
  });
  const pages = q.data?.pages ?? [];
  const counts = pages[0]?.counts;
  const listings = pages.flatMap((p) => p.items.map(toListing)).filter(byVerdict(s));
  return {
    listings,
    eligibleCount: counts?.eligible ?? 0,
    needsInputCount: counts?.needsInput ?? null,
    ineligibleCount: counts?.ineligible ?? null,
    remaining: null,
    hasMore: q.hasNextPage,
    loadMore: () => void q.fetchNextPage(),
    loading: q.isPending,
    loadingMore: q.isFetchingNextPage,
    error: q.isError,
  };
}

// USE_MOCKS는 빌드 때 정해지는 값이라 훅 순서가 바뀌지 않아요
export const useHomeList: (s: HomeListState) => HomeList = USE_MOCKS ? useMockList : useApiList;
