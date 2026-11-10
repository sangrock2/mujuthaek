"use client";

import { useState } from "react";
import { ageOf } from "@/features/conditions/format";
import { useConditions } from "@/features/conditions/store";
import { useRegions } from "@/features/regions/queries";
import type { BizStage } from "@/mocks/business";
import {
  emptyBizProfile,
  emptyBizSession,
  saveBizProfile,
  useBizProfileInput,
  type BizProfileInput,
  type BizSession,
} from "./profile";
import { useBusinessPreview } from "./queries";

/** 종류 필터: 전체 + 종류별 개수 */
export function useTypeFilter<K extends string, T extends { type: K }>(
  items: T[],
  initial: "all" | K = "all",
) {
  const [picked, setFilter] = useState<"all" | K | null>(null);
  // 처음에는 initial(사업 정보의 필요한 공간), 직접 고르면 그걸로
  const filter = picked ?? initial;
  const count = (key: "all" | K) =>
    key === "all" ? items.length : items.filter((i) => i.type === key).length;
  const visible = items.filter((i) => filter === "all" || i.type === filter);
  return { filter, setFilter, count, visible };
}

/**
 * 사업 정보 입력: 저장한 값(없으면 빈 값)에서 시작해 고치고, 저장하면 사업공간 · 사업 지원 판정에 써요.
 * 지역은 전국 시·도 → 시·군·구, 공통 정보(나이 · 사는 곳)는 조건 입력에서 가져와요
 */
export function useBizOnboardingForm() {
  const stored = useBizProfileInput();
  const conditions = useConditions();
  const regions = useRegions();
  const [edit, setEdit] = useState<{ draft: BizProfileInput; session: BizSession } | null>(null);
  const saved =
    stored.status === "ready"
      ? { draft: stored.profile ?? emptyBizProfile, session: stored.session }
      : { draft: emptyBizProfile, session: emptyBizSession };
  const { draft, session } = edit ?? saved;
  const set = (patch: Partial<BizProfileInput>) =>
    setEdit({ draft: { ...draft, ...patch }, session });
  const pre = draft.stage === "pre";
  const preview = useBusinessPreview(draft, session);
  const device = conditions.status === "ready" ? conditions.device : null;
  const age = device ? ageOf(device.birth) : null;
  const sidoCode = draft.regionCode.slice(0, 2);
  return {
    draft,
    stage: draft.stage,
    setStage: (stage: BizStage) => set({ stage }),
    pre,
    set,
    revenue: session.revenue,
    setRevenue: (revenue: string) => setEdit({ draft, session: { ...session, revenue } }),
    restrictions: session.restrictions,
    /** 신청 제한 사유 하나 켜고 끄기 (고르면 "해당 없음"은 풀려요) */
    toggleRestriction: (code: string) => {
      const cur = session.restrictions ?? [];
      const next = cur.includes(code) ? cur.filter((c) => c !== code) : [...cur, code];
      // 다 풀면 고르기 전으로 (빈 목록은 "해당 없음"이라 따로 눌러야 해요)
      setEdit({ draft, session: { ...session, restrictions: next.length ? next : null } });
    },
    /** 해당 없음 (다시 누르면 고르기 전으로) */
    toggleNoRestriction: () =>
      setEdit({
        draft,
        session: {
          ...session,
          restrictions: session.restrictions?.length === 0 ? null : [],
        },
      }),
    statuses: draft.statuses ?? null,
    /** 해당 유형 하나 켜고 끄기 (다 풀면 고르기 전으로) */
    toggleStatus: (code: string) => {
      const cur = draft.statuses ?? [];
      const next = cur.includes(code) ? cur.filter((c) => c !== code) : [...cur, code];
      set({ statuses: next.length ? next : null });
    },
    /** 해당 없음 (다시 누르면 고르기 전으로) */
    toggleNoStatus: () => set({ statuses: draft.statuses?.length === 0 ? null : [] }),
    needs: draft.needs,
    toggleNeed: (n: string) =>
      set({
        needs: draft.needs.includes(n) ? draft.needs.filter((x) => x !== n) : [...draft.needs, n],
      }),
    preview,
    /** 공통 정보 한 줄. 조건을 아직 안 넣었으면 null */
    common: device
      ? [
          age !== null && `만 ${age}세`,
          device.regionCode && `${regions.label(device.regionCode)} 거주`,
        ]
          .filter(Boolean)
          .join(" · ") || null
      : null,
    sidos: regions.sidos,
    sidoCode,
    sigungus: sidoCode ? (regions.sido(sidoCode)?.sigungus ?? []) : [],
    save: () => saveBizProfile(draft, { ...session, revenue: pre ? "" : session.revenue }),
  };
}

/** 준비 서류 체크 */
export function useDocChecks(initial: boolean[]) {
  const [checks, setChecks] = useState(initial);
  const toggle = (i: number) => setChecks((cur) => cur.map((v, j) => (j === i ? !v : v)));
  return { checks, toggle, done: checks.filter(Boolean).length };
}
