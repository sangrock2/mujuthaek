"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { toApplicant } from "@/features/conditions/applicant";
import { useConditions } from "@/features/conditions/store";
import { useCriteria } from "@/features/eligibility/criteria";
import { mockQuery } from "@/features/mock-query";
import { api } from "@/shared/lib/api/client";
import { USE_MOCKS } from "@/shared/lib/api/config";
import { endpoints } from "@/shared/lib/api/endpoints";
import { providerName } from "@/features/notice/labels";
import { formatWon } from "@/features/notice/format";
import { homeSummary, type HomeNewsItem, type HomeSummary } from "@/features/home/mocks/home";

export const homeKeys = {
  summary: ["home", "summary"] as const,
};

/** POST /api/v1/home/summary 응답 (백엔드 HomeSummaryResponse) */
type ApiNotice = {
  id: string;
  title: string;
  provider: string | null;
  noticeType: string | null;
  regionName: string | null;
  status: string;
  postedOn: string | null;
  applyEnd: string | null;
  dday: number | null;
  overall: "ELIGIBLE" | "NEEDS_INPUT" | "INELIGIBLE";
};

type ApiSummary = {
  homes: {
    eligible: number;
    needsInput: number;
    ineligible: number;
    newThisWeek: number;
    closingSoon: number;
  };
  benefits: { eligible: number; needsInput: number; annualAmountWon: number };
  suggestedBenefit: { id: string; title: string; amountText: string | null } | null;
  news: ApiNotice[];
  deadlines: ApiNotice[];
};

const org = (n: ApiNotice) => providerName(n.provider) ?? "공고";

/** 공고일까지 며칠 전인지 ("오늘" · "어제" · "3일 전") */
function agoLabel(postedOn: string, today: Date) {
  const days = Math.round(
    (Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()) -
      Date.parse(`${postedOn}T00:00:00Z`)) /
      86_400_000,
  );
  return days <= 0 ? "오늘" : days === 1 ? "어제" : `${days}일 전`;
}

/** "10월 25일" */
const monthDay = (iso: string) => {
  const [, m, d] = iso.split("-").map(Number);
  return `${m}월 ${d}일`;
};

const dueOf = (n: ApiNotice) =>
  n.status === "ALWAYS"
    ? "상시"
    : n.status === "UPCOMING"
      ? "접수 예정"
      : n.dday === null
        ? ""
        : n.dday <= 0
          ? "오늘 마감"
          : `D-${n.dday}`;

/** 응답 → 홈 카드 */
export function toHomeSummary(s: ApiSummary, today: Date): HomeSummary {
  return {
    homes: {
      count: s.homes.eligible,
      newThisWeek: s.homes.newThisWeek,
      closingSoon: s.homes.closingSoon,
    },
    benefits: {
      yearlyAmount: formatWon(s.benefits.annualAmountWon),
      count: s.benefits.eligible,
      needCheck: s.benefits.needsInput,
    },
    news: s.news.map((n): HomeNewsItem => ({
      id: n.id,
      kind: "notice",
      meta: ["새 공고", org(n), n.postedOn ? agoLabel(n.postedOn, today) : null]
        .filter(Boolean)
        .join(" · "),
      title: n.title,
      due: dueOf(n),
      verdict: n.overall === "ELIGIBLE" ? "ok" : "check",
    })),
    deadlines: s.deadlines.map((n) => ({
      id: n.id,
      title: n.title,
      meta: [org(n), n.applyEnd ? `접수 ${monthDay(n.applyEnd)}까지` : null]
        .filter(Boolean)
        .join(" · "),
      dday: Math.max(0, n.dday ?? 0),
    })),
    suggestedBenefit: s.suggestedBenefit
      ? { id: s.suggestedBenefit.id, title: s.suggestedBenefit.title }
      : null,
  };
}

/** 실제 API: 내 조건(구간 값)과 찾아볼 지역으로 홈 요약을 받아요. 조건이 든 결과라 짧게만 둬요 */
function useApiHomeSummary() {
  const stored = useConditions();
  const criteria = useCriteria();
  const ready = stored.status === "ready" && (stored.device === null || !criteria.isPending);
  const device = stored.status === "ready" ? stored.device : null;
  const body = useMemo(() => {
    if (stored.status !== "ready") return null;
    // 찾아볼 지역(이사갈 곳)만 써요. 없으면 전체
    const regionCodes = device?.searchRegionCodes ?? [];
    return {
      filters: regionCodes.length ? { regionCodes } : {},
      applicant: toApplicant(stored.device, stored.session, criteria.data),
    };
  }, [stored, device, criteria.data]);

  return useQuery({
    queryKey: [...homeKeys.summary, body] as const,
    queryFn: async () =>
      toHomeSummary(await api.post<ApiSummary>(endpoints.homeSummary, body), new Date()),
    enabled: ready && body !== null,
    staleTime: 60 * 1000,
    gcTime: 5 * 60 * 1000,
  });
}

function useMockHomeSummary() {
  return useQuery(mockQuery(homeKeys.summary, homeSummary));
}

// USE_MOCKS는 빌드 때 정해지는 값이라 훅 순서가 바뀌지 않아요
const useSummaryQuery = USE_MOCKS ? useMockHomeSummary : useApiHomeSummary;

const emptySummary: HomeSummary = {
  homes: { count: 0, newThisWeek: 0, closingSoon: 0 },
  benefits: null,
  news: [],
  deadlines: [],
  suggestedBenefit: null,
};

/** 홈 요약. 받기 전엔 빈 값 + loading, 못 받으면 error */
export function useHomeSummary(personalized: boolean) {
  const q = useSummaryQuery();
  const data = q.data ?? emptySummary;
  const loading = q.isPending;
  const error = q.isError;
  const count = (value: number) => (loading ? "…" : `${value}곳`);
  const homes = {
    label: personalized ? "지원 가능한 청약·공공임대" : "청약·공공임대 공고",
    value: personalized ? (error ? "–" : count(data.homes.count)) : "공고 둘러보기",
    note: error
      ? "공고를 불러오지 못했어요"
      : `이번 주 새로 ${count(data.homes.newThisWeek)} · 마감 임박 ${count(data.homes.closingSoon)}`,
  };
  const benefits = {
    label: personalized ? "받을 수 있는 혜택" : "주거 혜택",
    value: personalized
      ? error
        ? "–"
        : loading
          ? "…"
          : data.benefits
            ? `연 ${data.benefits.yearlyAmount}`
            : "–"
      : "혜택 둘러보기",
    note: !personalized
      ? "월세 지원·대출 등 주거 지원 정책"
      : error
        ? "혜택을 불러오지 못했어요"
        : data.benefits
          ? `${data.benefits.count}개 · 확인 필요 ${data.benefits.needCheck}개`
          : "받을 수 있는 혜택을 판정하고 있어요",
  };
  return { data, loading, error, homes, benefits };
}
