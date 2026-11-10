"use client";

import { keepPreviousData, useQueries } from "@tanstack/react-query";
import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { toBenefit, useJudgeInput, type ApiBenefitSearch } from "@/features/benefits/api";
import {
  toSpaceItem,
  toSupportItem,
  useSpaceApplicant,
  type ApiSpaceSearch,
  type ApiSupportSearch,
} from "@/features/business/api";
import { toListing, type SearchResponse } from "@/features/homes/search";
import { api } from "@/lib/api/client";
import { USE_MOCKS } from "@/lib/api/config";
import { endpoints } from "@/lib/api/endpoints";
import { routes } from "@/lib/routes";
import { searchData, type SearchBadge, type SearchResult, type SearchType } from "@/mocks/search";

/** 지역(동네) 검색은 아직 API가 없어 목업에서만 보여요 */
export const searchTypes: SearchType[] = USE_MOCKS ? ["공고", "혜택", "지역"] : ["공고", "혜택"];

export type SearchTab = "전체" | SearchType;

export const resultHref = (r: SearchResult) =>
  r.href ??
  (r.type === "공고"
    ? routes.notice(r.id)
    : r.type === "혜택"
      ? routes.benefit(r.id)
      : routes.homes);

const RECENT_KEY = "mujuthaek.search.recent";
const RECENT_MAX = 8;
/** 종류마다 한 번에 받는 수 (서버 최대). 넘으면 검색어로 좁혀 달라고 해요 */
const SIZE = 100;

function readRecent(): string[] {
  try {
    const v = JSON.parse(window.localStorage.getItem(RECENT_KEY) ?? "[]");
    return Array.isArray(v) ? v.filter((s) => typeof s === "string").slice(0, RECENT_MAX) : [];
  } catch {
    return [];
  }
}

const badgeOf = (overall: "ELIGIBLE" | "NEEDS_INPUT" | "INELIGIBLE"): SearchBadge =>
  overall === "ELIGIBLE"
    ? { kind: "ok" }
    : overall === "INELIGIBLE"
      ? { kind: "none" }
      : { kind: "check" };

const meta = (...parts: (string | null | undefined)[]) => parts.filter(Boolean).join(" · ");

/**
 * 검색: 검색어로 주거 공고 · 사업공간(공고) 와 혜택 · 사업 지원(혜택)을 찾아 내 판정 배지와 함께 보여줘요.
 * 검색어가 없으면 열린 것 전부(맞춤 목록 순서). 판정 입력은 맞춤 목록과 같은 구간 값이에요. 최근 검색어는 이 기기에만 저장해요
 */
export function useSearch() {
  const [query, setQuery] = useState(USE_MOCKS ? searchData.query : "");
  const [recent, setRecent] = useState<string[]>(USE_MOCKS ? searchData.recent : []);
  useEffect(() => {
    if (USE_MOCKS) return;
    const q = new URLSearchParams(window.location.search).get("q");
    // 처음 열 때 한 번만 브라우저 값(주소의 검색어, 최근 검색어)을 읽어요
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (q) setQuery(q);
    setRecent(readRecent());
  }, []);

  const keyword = useDeferredValue(query.trim());
  const judge = useJudgeInput();
  const space = useSpaceApplicant();
  const enabled = !USE_MOCKS;
  const common = { staleTime: 60 * 1000, placeholderData: keepPreviousData } as const;

  const [notices, spaces, benefits, supports] = useQueries({
    queries: [
      {
        queryKey: ["search", "notices", keyword, judge.applicant] as const,
        queryFn: () =>
          api.post<SearchResponse>(endpoints.noticesSearch, {
            filters: { keyword: keyword || undefined },
            applicant: judge.applicant,
            includeIneligible: true,
            size: SIZE,
          }),
        enabled: enabled && judge.ready,
        ...common,
      },
      {
        queryKey: ["search", "spaces", keyword, space.applicant] as const,
        queryFn: () =>
          api.post<ApiSpaceSearch>(endpoints.spacesSearch, {
            filters: { keyword: keyword || undefined },
            applicant: space.applicant,
            includeIneligible: true,
            size: SIZE,
          }),
        enabled: enabled && space.ready,
        ...common,
      },
      {
        queryKey: ["search", "benefits", keyword, judge.applicant] as const,
        queryFn: () =>
          api.post<ApiBenefitSearch>(endpoints.benefitsSearch, {
            filters: { keyword: keyword || undefined },
            applicant: judge.applicant,
            size: SIZE,
          }),
        enabled: enabled && judge.ready,
        ...common,
      },
      {
        queryKey: ["search", "supports", keyword, space.applicant] as const,
        queryFn: () =>
          api.post<ApiSupportSearch>(endpoints.supportsSearch, {
            filters: { keyword: keyword || undefined },
            applicant: space.applicant,
            includeIneligible: true,
            size: SIZE,
          }),
        enabled: enabled && space.ready,
        ...common,
      },
    ],
  });

  const results: SearchResult[] = useMemo(() => {
    if (USE_MOCKS) return searchData.results;
    return [
      ...(notices.data?.items ?? []).map((it): SearchResult => {
        const l = toListing(it);
        return {
          id: it.id,
          type: "공고",
          title: it.title,
          meta: meta(l.org, it.regionName, l.due),
          metaShort: meta(l.org, l.due),
          badge: badgeOf(it.overall),
        };
      }),
      ...(spaces.data?.items ?? []).map((it): SearchResult => {
        const s = toSpaceItem(it);
        return {
          id: it.id,
          type: "공고",
          title: it.title,
          meta: meta(s.org, s.info),
          metaShort: meta(s.org, s.due),
          badge: badgeOf(it.overall),
          href: routes.space(it.id),
        };
      }),
      ...(benefits.data?.items ?? []).map((it): SearchResult => {
        const b = toBenefit(it);
        return {
          id: it.id,
          type: "혜택",
          title: it.title,
          meta: meta(b.org, b.amount, b.deadline),
          metaShort: meta(b.orgShort, b.dday),
          badge: badgeOf(it.overall),
        };
      }),
      ...(supports.data?.items ?? []).map((it): SearchResult => {
        const s = toSupportItem(it);
        return {
          id: it.id,
          type: "혜택",
          title: it.title,
          meta: meta(s.org, s.body, s.note),
          metaShort: meta(s.org, s.due),
          badge: badgeOf(it.overall),
          href: s.href,
        };
      }),
    ];
  }, [notices.data, spaces.data, benefits.data, supports.data]);

  const sum = (c?: { eligible: number; needsInput: number; ineligible: number }) =>
    c ? c.eligible + c.needsInput + c.ineligible : 0;
  /** 종류별 전체 수 (받은 것보다 많을 수 있어요). 혜택 정책은 지원 불가를 빼고 줘요 */
  const totals: Record<SearchType, number> = USE_MOCKS
    ? {
        공고: results.filter((r) => r.type === "공고").length,
        혜택: results.filter((r) => r.type === "혜택").length,
        지역: results.filter((r) => r.type === "지역").length,
      }
    : {
        공고: sum(notices.data?.counts) + sum(spaces.data?.counts),
        혜택:
          (benefits.data ? benefits.data.summary.eligible + benefits.data.summary.needsInput : 0) +
          sum(supports.data?.counts),
        지역: 0,
      };

  const queries = [notices, spaces, benefits, supports];
  /** 고른 검색어를 최근 검색어 맨 앞에 둬요 (이 기기에만) */
  const remember = (q = query) => {
    const t = q.trim();
    if (!t || USE_MOCKS) return;
    const next = [t, ...recent.filter((r) => r !== t)].slice(0, RECENT_MAX);
    setRecent(next);
    try {
      window.localStorage.setItem(RECENT_KEY, JSON.stringify(next));
    } catch {
      // 저장을 못 해도 검색은 돼요
    }
  };

  return {
    query,
    setQuery,
    keyword,
    recent,
    remember,
    terms: USE_MOCKS ? searchData.terms : keyword.split(/\s+/).filter(Boolean),
    results,
    totals,
    /** 받은 것보다 더 있는 종류 (검색어로 좁혀 달라고 해요) */
    more: {
      공고: Boolean(notices.data?.hasNext || spaces.data?.hasNext),
      혜택: Boolean(benefits.data?.hasNext || supports.data?.hasNext),
      지역: false,
    } as Record<SearchType, boolean>,
    loading: enabled && queries.some((q) => q.isFetching),
    error: enabled && queries.some((q) => q.isError),
  };
}

/** 제목을 검색어 기준으로 잘라 강조할 부분을 표시해요 */
export function splitTitle(text: string, terms: string[]) {
  if (terms.length === 0) return [{ t: text, hl: false }];
  const escaped = terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const re = new RegExp(`(${escaped.join("|")})`, "gi");
  const lower = terms.map((t) => t.toLowerCase());
  return text
    .split(re)
    .filter(Boolean)
    .map((t) => ({ t, hl: lower.includes(t.toLowerCase()) }));
}

/** 분류 탭에 맞는 섹션들 */
export function groupResults(
  results: SearchResult[],
  tab: SearchTab,
  totals: Record<SearchType, number>,
) {
  const types = tab === "전체" ? searchTypes : [tab];
  return types.map((type) => {
    const rows = results.filter((r) => r.type === type);
    return { type, count: Math.max(totals[type], rows.length), rows };
  });
}
