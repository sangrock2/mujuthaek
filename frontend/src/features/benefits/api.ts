"use client";

import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { toApplicant } from "@/features/conditions/applicant";
import { inputHrefOf } from "@/features/conditions/needs";
import { useConditions } from "@/features/conditions/store";
import { useCriteria } from "@/features/eligibility/criteria";
import { formatWon } from "@/features/notice/format";
import { api } from "@/lib/api/client";
import { endpoints } from "@/lib/api/endpoints";
import type { Benefit, BenefitCategory, BenefitEligibility } from "@/mocks/benefits";

type ApiOverall = "ELIGIBLE" | "NEEDS_INPUT" | "INELIGIBLE";
type ApiApplyStatus = "UPCOMING" | "APPLYING" | "CLOSED" | "ALWAYS";

/** POST /api/v1/benefits/search 한 줄 (백엔드 BenefitSearchResponse.Item) */
type ApiBenefitItem = {
  id: string;
  title: string;
  agency: string | null;
  category: "HOUSING" | "ASSET" | "TRANSPORT";
  summary: string | null;
  regionNames: string[];
  amountText: string | null;
  annualAmountWon: number;
  applyStatus: ApiApplyStatus;
  applyEnd: string | null;
  dday: number | null;
  overall: ApiOverall;
  affectsPrepareCost: boolean;
  needsReview: boolean;
};

type ApiBenefitSearch = {
  summary: { eligible: number; needsInput: number; ineligible: number; annualAmountWon: number };
  categoryCounts: Record<string, number>;
  items: ApiBenefitItem[];
  nextCursor: string | null;
  hasNext: boolean;
};

/** GET /api/v1/benefits/{id} (백엔드 BenefitDetailResponse) */
type ApiBenefitDetail = {
  header: {
    id: string;
    title: string;
    agency: string | null;
    category: ApiBenefitItem["category"];
    summary: string | null;
    applyStatus: ApiApplyStatus;
    applyStart: string | null;
    applyEnd: string | null;
    dday: number | null;
    scheduleText: string | null;
    needsReview: boolean;
  };
  supports: {
    kind: string;
    amountMaxWon: number | null;
    amountPer: string | null;
    months: number | null;
    ratePct: number | null;
    rawText: string;
  }[];
  howToApply: string | null;
  documents: string[];
  contact: string | null;
  conditions: { type: string; group: number; known: boolean; rawText: string; evidence: string }[];
  sources: { sourceCode: string; detailUrl: string | null; applyUrl: string | null }[];
};

type ApiStatus = "MET" | "NOT_MET" | "UNKNOWN";

/** POST /api/v1/benefits/{id}/evaluate (백엔드 BenefitEvaluationResponse) */
type ApiBenefitEvaluation = {
  overall: ApiOverall;
  reason: string | null;
  conditions: {
    group: number;
    status: ApiStatus;
    items: { label: string; status: ApiStatus; reason: string | null; needs: string[] }[];
  }[];
  notes: string[];
  annualAmountWon: number;
};

const categoryOf: Record<ApiBenefitItem["category"], BenefitCategory> = {
  HOUSING: "주거",
  ASSET: "자산형성",
  TRANSPORT: "교통",
};

export const categoryCode: Record<BenefitCategory, ApiBenefitItem["category"]> = {
  주거: "HOUSING",
  자산형성: "ASSET",
  교통: "TRANSPORT",
};

const resultOf: Record<ApiStatus, BenefitEligibility["result"]> = {
  MET: "ok",
  UNKNOWN: "check",
  NOT_MET: "no",
};

/** "2026-11-30" → "11월 30일" */
const monthDay = (iso: string) => {
  const [, m, d] = iso.split("-").map(Number);
  return `${m}월 ${d}일`;
};

function ddayLabel(status: ApiApplyStatus, dday: number | null) {
  if (status === "ALWAYS") return "상시";
  if (status === "UPCOMING") return "신청 전";
  if (dday === null) return "기한 확인";
  return dday <= 0 ? "오늘 마감" : `D-${dday}`;
}

function deadlineLabel(status: ApiApplyStatus, start: string | null, end: string | null) {
  if (status === "ALWAYS") return "상시 신청";
  if (status === "UPCOMING" && start) return `${monthDay(start)}부터`;
  return end ? `${monthDay(end)}까지` : "원문 확인";
}

/** 기관 이름이 길면 앞 부분만 (모바일 목록) */
const shortOrg = (org: string) => org.split(/[·\s]/)[0] || org;

const LOANS = ["DEPOSIT_LOAN", "PURCHASE_LOAN", "LOAN"];

/** 지원 내용 한 줄 (목록 없이 상세로 바로 들어왔을 때. 백엔드 amountText와 같은 규칙) */
function supportText(s: ApiBenefitDetail["supports"][number]) {
  const per = s.amountPer === "MONTH" ? "월 " : s.amountPer === "YEAR" ? "연 " : "";
  const loan = LOANS.includes(s.kind);
  const amount =
    s.amountMaxWon !== null
      ? `${per}최대 ${formatWon(s.amountMaxWon)}${loan ? " 대출" : ""}`
      : null;
  const months = s.months !== null ? `${s.months}개월` : null;
  const rate =
    amount === null && s.ratePct !== null ? `${loan ? "이자 " : ""}${s.ratePct}% 지원` : null;
  return [amount, months, rate].filter(Boolean).join(" · ") || s.rawText;
}

/** 목록 한 줄 → 화면 혜택 (상세 칸은 비워 두고 고른 뒤 채워요) */
export function toBenefit(i: ApiBenefitItem): Benefit {
  const org = i.agency ?? i.regionNames[0] ?? "기관";
  const amount = i.amountText ?? i.summary ?? "지원 내용 확인";
  return {
    id: i.id,
    cat: categoryOf[i.category],
    org,
    orgShort: shortOrg(org),
    title: i.title,
    amount,
    amountShort: amount,
    dday: ddayLabel(i.applyStatus, i.dday),
    deadline: deadlineLabel(i.applyStatus, null, i.applyEnd),
    verdict: i.overall === "ELIGIBLE" ? "ok" : "check",
    budget: i.affectsPrepareCost,
    overlap: "",
    elig: [],
    how: [],
    docs: "",
    sourceUrl: "",
    policyUrl: "",
    applyUrl: "",
  };
}

/** 상세 + 판정 → 화면 혜택 */
export function toBenefitDetail(
  d: ApiBenefitDetail,
  e: ApiBenefitEvaluation | undefined,
  base: Benefit | undefined,
): Benefit {
  const h = d.header;
  const org = h.agency ?? base?.org ?? "기관";
  const source = d.sources[0];
  const elig: BenefitEligibility[] = e
    ? e.conditions.map((g) => ({
        label: g.items.map((i) => i.label).join(" 또는 "),
        result: resultOf[g.status],
        reason:
          g.status === "MET" ? undefined : (g.items.find((i) => i.reason)?.reason ?? undefined),
        inputHref:
          g.status === "UNKNOWN"
            ? inputHrefOf(g.items.filter((i) => i.status === "UNKNOWN").flatMap((i) => i.needs))
            : undefined,
      }))
    : d.conditions
        .filter((c) => c.type !== "EXCLUSIVE" && c.type !== "PRIORITY")
        .map((c) => ({ label: c.rawText, result: "check" as const }));
  const exclusive = e
    ? e.notes
    : d.conditions.filter((c) => c.type === "EXCLUSIVE").map((c) => c.rawText);
  const support = d.supports[0];
  const amount = base?.amount || (support ? supportText(support) : "지원 내용 확인");
  return {
    id: h.id,
    cat: categoryOf[h.category],
    org,
    orgShort: shortOrg(org),
    title: h.title,
    amount,
    amountShort: amount,
    dday: ddayLabel(h.applyStatus, h.dday),
    deadline: deadlineLabel(h.applyStatus, h.applyStart, h.applyEnd),
    verdict: e ? (e.overall === "ELIGIBLE" ? "ok" : "check") : (base?.verdict ?? "check"),
    budget: d.supports.some((s) => s.kind === "DEPOSIT_LOAN" || s.kind === "PURCHASE_LOAN"),
    overlap: exclusive.length ? exclusive.join(" · ") : "원문에 적힌 제한이 없어요",
    elig,
    how: d.howToApply ? [d.howToApply] : [],
    docs: d.documents.length ? d.documents.join(", ") : "원문을 확인해 주세요",
    sourceUrl: source?.detailUrl ?? "",
    policyUrl: source?.detailUrl ?? "",
    applyUrl: source?.applyUrl ?? source?.detailUrl ?? "",
    reason: e?.reason ?? undefined,
  };
}

/** 판정 입력 (구간 값)과 찾아볼 지역 */
export function useJudgeInput() {
  const stored = useConditions();
  const criteria = useCriteria();
  const ready = stored.status === "ready" && !criteria.isPending;
  const applicant = useMemo(
    () =>
      stored.status === "ready" ? toApplicant(stored.device, stored.session, criteria.data) : {},
    [stored, criteria.data],
  );
  const regionCodes = stored.status === "ready" ? (stored.device?.searchRegionCodes ?? []) : [];
  return { ready, applicant, regionCodes };
}

const PAGE_SIZE = 20;

/** 혜택 맞춤 목록 (찾아볼 지역, 구간 값). 조건이 든 결과라 짧게만 둬요 */
export function useBenefitSearch() {
  const { ready, applicant, regionCodes } = useJudgeInput();
  return useInfiniteQuery({
    queryKey: ["benefits", "search", regionCodes, applicant] as const,
    queryFn: ({ pageParam }) =>
      api.post<ApiBenefitSearch>(endpoints.benefitsSearch, {
        filters: { regionCodes },
        applicant,
        cursor: pageParam,
        size: PAGE_SIZE,
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => (last.hasNext ? last.nextCursor : null),
    enabled: ready,
    staleTime: 60 * 1000,
    gcTime: 5 * 60 * 1000,
    placeholderData: keepPreviousData,
  });
}

/** 혜택 하나: 공개 상세 + 내 판정 */
export function useBenefitDetailQuery(id: string | undefined, base: Benefit | undefined) {
  const { ready, applicant } = useJudgeInput();
  const detail = useQuery({
    queryKey: ["benefits", "detail", id] as const,
    queryFn: () => api.get<ApiBenefitDetail>(endpoints.benefitDetail(id!)),
    enabled: Boolean(id),
    staleTime: 5 * 60 * 1000,
  });
  const evaluation = useQuery({
    queryKey: ["benefits", "evaluate", id, applicant] as const,
    queryFn: () => api.post<ApiBenefitEvaluation>(endpoints.benefitEvaluate(id!), { applicant }),
    enabled: Boolean(id) && ready,
    staleTime: 60 * 1000,
    gcTime: 5 * 60 * 1000,
  });
  const data = useMemo(
    () => (detail.data ? toBenefitDetail(detail.data, evaluation.data, base) : undefined),
    [detail.data, evaluation.data, base],
  );
  return { data, loading: detail.isPending, error: detail.isError };
}

export type { ApiBenefitSearch };
