"use client";

import { useEffect } from "react";
import { useConditions } from "@/features/conditions/store";
import { track } from "@/lib/analytics";
import type { Notice } from "@/mocks/notice";

/** 방문 통계에 붙이는 공고 정보: 기관과 시·도만(개인 정보 없음). 공고 종류는 판정 화면 종류(kind)로 */
export function noticeParams(n: Notice): Record<string, string> {
  if (n.kind !== "standard") return { notice_kind: n.kind };
  return {
    notice_kind: n.kind,
    agency: n.agency || "-",
    region: (n.benefitArea ?? "").split(" ")[0] || "-",
  };
}

// 웹·모바일 화면이 함께 그려져도(보이는 건 하나) 같은 공고는 잠깐 안에 한 번만 보내요
const sentAt = new Map<string, number>();
const ONCE_MS = 3000;

/** 조건을 넣은 사람이 공고 상세(판정 결과)를 열면 「판정 실행」을 한 번 보내요. 공고를 불러오는 중(undefined)이면 기다려요 */
export function useJudgmentViewed(id: string, n: Notice | undefined) {
  const conditions = useConditions();
  const ready = conditions.status === "ready";
  const hasConditions = ready && Boolean(conditions.device || conditions.session);
  useEffect(() => {
    if (!hasConditions || !n) return;
    const now = Date.now();
    if (now - (sentAt.get(id) ?? 0) < ONCE_MS) return;
    sentAt.set(id, now);
    track("judgment_run", noticeParams(n));
    // 공고가 바뀔 때만 다시 보내요
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, hasConditions, Boolean(n)]);
}
