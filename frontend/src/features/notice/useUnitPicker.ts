"use client";

import { useState } from "react";
import type { NoticeUnit } from "@/mocks/notice";

/** 공급 주택 목록: 신청 가능만 보기 + 집 하나 고르기 */
export function useUnitPicker(units: NoticeUnit[]) {
  const [onlyOk, setOnlyOk] = useState(false);
  const [picked, setPicked] = useState<string | null>(units[0]?.id ?? null);

  const shown = onlyOk ? units.filter((u) => u.ok) : units;
  // 필터로 고른 집이 숨겨지면 목록의 첫 집을 골라요
  const selected = shown.find((u) => u.id === picked) ?? shown[0] ?? null;

  return {
    onlyOk,
    setOnlyOk,
    shown,
    selected,
    select: (id: string) => setPicked(id),
    countAll: units.length,
    countOk: units.filter((u) => u.ok).length,
  };
}

export const unitStatus = (u: NoticeUnit) => (u.ok ? "신청 가능" : u.otherTarget);
