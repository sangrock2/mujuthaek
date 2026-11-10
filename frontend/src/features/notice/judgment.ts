"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import type { ListingVerdict } from "@/components/ui/Badge";
import { availableCashWon, toApplicant } from "@/features/conditions/applicant";
import { inputHrefOf } from "@/features/conditions/needs";
import { useConditions } from "@/features/conditions/store";
import { useCriteria } from "@/features/eligibility/criteria";
import { formatWon } from "@/features/notice/format";
import { prepareNoteLabel } from "@/features/notice/labels";
import { api } from "@/lib/api/client";
import { USE_MOCKS } from "@/lib/api/config";
import { endpoints } from "@/lib/api/endpoints";
import { routes } from "@/lib/routes";
import type { NoticeMoney, StandardNotice } from "@/mocks/notice";
import type { NoticeDoc } from "@/mocks/notice-doc";

type ApiStatus = "MET" | "NOT_MET" | "UNKNOWN";
type ApiOverall = "ELIGIBLE" | "NEEDS_INPUT" | "INELIGIBLE";

type ApiItem = {
  id: string;
  key: string;
  label: string;
  status: ApiStatus;
  reason: string | null;
  needs: string[];
  evidence: { text: string; page: number | null } | null;
  options: { label: string; status: ApiStatus; items: ApiItem[] }[] | null;
};

/** POST /api/v1/eligibility/notices/{id}/evaluate 응답 (백엔드 NoticeEvaluationResponse) */
export type ApiEvaluation = {
  noticeId: string;
  overall: ApiOverall;
  reason: string | null;
  targets: {
    id: string;
    name: string;
    overall: ApiOverall;
    summary: { total: number; met: number; notMet: number; unknown: number };
    items: ApiItem[];
  }[];
  missingInputs: string[];
  unitTypes: {
    houseType: string;
    eligible: boolean;
    prepareCost: {
      depositWon: number | null;
      loan: { productCode: string; name: string; amountWon: number } | null;
      prepareWon: number | null;
      note: string | null;
    };
  }[];
};

/** met: 충족 · notMet: 해당 안 됨 · unknown: 확인 필요 */
export type CheckStatus = "met" | "notMet" | "unknown";

export type JudgedItem = {
  id: string;
  /** PC 문구 */
  label: string;
  /** 모바일 문구 (없으면 label) */
  shortLabel?: string;
  status: CheckStatus;
  /** 충족이 아닐 때 이유 (기준만, 내 값은 없어요) */
  reason?: string;
  /** 넣으면 판정되는 입력을 받는 화면. 없으면 원문 확인이에요 */
  inputHref?: string;
  /** 근거 원문 쪽 */
  page?: number;
};

export type JudgedTarget = {
  id: string;
  /** 공급 대상 이름 (한 대상뿐이면 빈 문자열) */
  name: string;
  verdict: ListingVerdict;
  counts: { met: number; notMet: number; unknown: number };
  items: JudgedItem[];
};

export type NoticeJudgment = {
  verdict: ListingVerdict;
  /** 판정할 수 없을 때 이유 (판정 틀이 아직 없음 등) */
  reason?: string;
  /** 유리한 대상부터 (지원 가능 → 확인 필요 → 지원 불가) */
  targets: JudgedTarget[];
  money?: NoticeMoney;
  /** 내 조건으로 신청할 수 있는 주택형 */
  mineTypes: string[];
  /** 주택형별 준비할 돈 ("960만 원" · 모르면 이유) */
  prepByType: Record<string, string>;
};

const verdictOf: Record<ApiOverall, ListingVerdict> = {
  ELIGIBLE: "ok",
  NEEDS_INPUT: "check",
  INELIGIBLE: "no",
};

const statusOf: Record<ApiStatus, CheckStatus> = {
  MET: "met",
  NOT_MET: "notMet",
  UNKNOWN: "unknown",
};

const order: Record<ListingVerdict, number> = { ok: 0, check: 1, no: 2 };

function itemOf(i: ApiItem): JudgedItem {
  // 직접 묻는 조건(ASK)은 이유가 질문 그대로라 한 번만 보여줘요
  const reason = i.reason && i.reason !== i.label ? i.reason : undefined;
  return {
    id: i.id,
    label: i.label,
    status: statusOf[i.status],
    reason,
    inputHref: inputHrefOf(i.needs),
    page: i.evidence?.page ?? undefined,
  };
}

/** 준비할 돈: 신청할 수 있는 주택형 중 가장 적게 드는 것 (없으면 전체 중) */
function moneyOf(
  e: ApiEvaluation,
  rentOf: (houseType: string) => number | null,
  cashWon: number | null,
): NoticeMoney | undefined {
  if (!e.unitTypes.length) return undefined;
  const mine = e.unitTypes.filter((u) => u.eligible);
  const pool = mine.length ? mine : e.unitTypes;
  const known = pool.filter((u) => u.prepareCost.prepareWon !== null);
  const pick = known.length
    ? known.reduce((a, b) => (b.prepareCost.prepareWon! < a.prepareCost.prepareWon! ? b : a))
    : pool[0];
  const { depositWon, loan, prepareWon, note } = pick.prepareCost;
  const rent = rentOf(pick.houseType);
  const cash =
    cashWon === null || prepareWon === null
      ? null
      : cashWon >= prepareWon
        ? "쓸 수 있는 돈으로 준비할 수 있어요"
        : `쓸 수 있는 돈보다 ${formatWon(prepareWon - cashWon)} 더 필요해요`;
  return {
    type: pick.houseType,
    deposit: depositWon === null ? "원문 확인" : formatWon(depositWon),
    loanName: loan ? `${loan.name} 예상` : undefined,
    loanShortName: loan
      ? `${loan.name.replace(/\s*(전세자금\s*)?대출$/, "")} 대출 예상`
      : undefined,
    loan: loan ? formatWon(loan.amountWon) : undefined,
    prep:
      prepareWon !== null ? formatWon(prepareWon) : (prepareNoteLabel[note ?? ""] ?? "확인 필요"),
    note: [rent !== null && `월 임대료 ${formatWon(rent)}`, cash].filter(Boolean).join(" · "),
  };
}

/** 판정 응답 → 화면 값. cashWon은 브라우저에만 있는 쓸 수 있는 돈 (서버로 보내지 않아요) */
export function toJudgment(
  e: ApiEvaluation,
  notice: StandardNotice,
  cashWon: number | null,
): NoticeJudgment {
  const rents = new Map(
    notice.doc.housing.flatMap((h) => h.types.map((t) => [t.code, t.monthlyRentWon] as const)),
  );
  const targets = e.targets
    .map((t): JudgedTarget => ({
      id: t.id,
      name: t.name,
      verdict: verdictOf[t.overall],
      counts: { met: t.summary.met, notMet: t.summary.notMet, unknown: t.summary.unknown },
      items: t.items.map(itemOf),
    }))
    .sort((a, b) => order[a.verdict] - order[b.verdict]);
  return {
    verdict: verdictOf[e.overall],
    reason: e.reason ?? undefined,
    targets,
    money: moneyOf(e, (k) => rents.get(k) ?? null, cashWon),
    mineTypes: e.unitTypes.filter((u) => u.eligible).map((u) => u.houseType),
    prepByType: Object.fromEntries(
      e.unitTypes.map((u) => [
        u.houseType,
        u.prepareCost.prepareWon !== null
          ? formatWon(u.prepareCost.prepareWon)
          : (prepareNoteLabel[u.prepareCost.note ?? ""] ?? "확인 필요"),
      ]),
    ),
  };
}

/** 목업 공고의 판정 (대상 하나) */
export function mockJudgment(n: StandardNotice): NoticeJudgment {
  const items = n.eligibility.map((e): JudgedItem => ({
    id: e.label,
    label: e.label,
    shortLabel: e.shortLabel,
    status: e.status === "met" ? "met" : "unknown",
    inputHref: e.status === "input" ? routes.profile : undefined,
  }));
  const count = (s: CheckStatus) => items.filter((i) => i.status === s).length;
  return {
    verdict: n.verdict,
    targets: [
      {
        id: "all",
        name: "",
        verdict: n.verdict,
        counts: { met: count("met"), notMet: count("notMet"), unknown: count("unknown") },
        items,
      },
    ],
    money: n.money,
    mineTypes: n.doc.housing.flatMap((h) => h.types.filter((t) => t.mine).map((t) => t.code)),
    prepByType: {},
  };
}

/** 주택형 표에 내 조건으로 신청할 수 있는 주택형을 표시해요 */
export function withMine(doc: NoticeDoc, mineTypes: string[]): NoticeDoc {
  if (!mineTypes.length) return doc;
  return {
    ...doc,
    housing: doc.housing.map((h) => ({
      ...h,
      types: h.types.map((t) => ({ ...t, mine: mineTypes.includes(t.code) })),
    })),
  };
}

type JudgmentState = { judgment: NoticeJudgment | null; loading: boolean; error: boolean };

/** 실제 API: 내 조건(구간 값)으로 공고 하나를 판정해요. 조건이 든 결과라 짧게만 둬요 */
function useApiJudgment(notice: StandardNotice | undefined): JudgmentState {
  const stored = useConditions();
  const criteria = useCriteria();
  const ready = stored.status === "ready" && !criteria.isPending;
  const applicant = useMemo(
    () =>
      stored.status === "ready" ? toApplicant(stored.device, stored.session, criteria.data) : {},
    [stored, criteria.data],
  );
  const cashWon = stored.status === "ready" ? availableCashWon(stored.session) : null;
  const id = notice?.id ?? "";

  const q = useQuery({
    queryKey: ["notice", "evaluate", id, applicant] as const,
    queryFn: () =>
      api.post<ApiEvaluation>(endpoints.noticeEvaluate(id), {
        applicant,
      }),
    enabled: ready && Boolean(notice),
    staleTime: 60 * 1000,
    gcTime: 5 * 60 * 1000,
  });

  const judgment = useMemo(
    () => (q.data && notice ? toJudgment(q.data, notice, cashWon) : null),
    [q.data, notice, cashWon],
  );
  return { judgment, loading: !judgment && !q.isError, error: q.isError };
}

function useMockJudgment(notice: StandardNotice | undefined): JudgmentState {
  const judgment = useMemo(() => (notice ? mockJudgment(notice) : null), [notice]);
  return { judgment, loading: false, error: false };
}

// USE_MOCKS는 빌드 때 정해지는 값이라 훅 순서가 바뀌지 않아요
export const useNoticeJudgment = USE_MOCKS ? useMockJudgment : useApiJudgment;
