"use client";

// 내 집 목록의 입주 방식 · 정렬 · 유형 · 판정 필터 상태 (웹 왼쪽 칸 · 모바일 필터 시트가 같이 써요)
import { useState } from "react";
import {
  changedFilterCount,
  defaultChecked,
  defaultMode,
  defaultSort,
  noticeTypesOf,
  type FilterKey,
  type MoveInMode,
  type SortOption,
} from "./filters";

export function useHomesFilters() {
  const [mode, setMode] = useState<MoveInMode>(defaultMode);
  const [sort, setSort] = useState<SortOption>(defaultSort);
  const [checked, setChecked] = useState(defaultChecked);
  return {
    mode,
    setMode,
    sort,
    setSort,
    checked,
    toggle: (key: FilterKey, on: boolean) => setChecked((prev) => ({ ...prev, [key]: on })),
    showIneligible: () => setChecked((prev) => ({ ...prev, ineligible: true })),
    /** 입주 방식 · 정렬 · 체크를 처음으로 (지역은 부르는 쪽에서) */
    reset: () => {
      setMode(defaultMode);
      setSort(defaultSort);
      setChecked(defaultChecked);
    },
    changedCount: changedFilterCount(checked, mode, sort),
    /** useHomeList에 넘길 값 */
    listState: {
      mode,
      sort,
      noticeTypes: noticeTypesOf(checked),
      includeIneligible: checked.ineligible,
      showOk: checked.ok,
      showCheck: checked.check,
    },
  };
}

export type HomesFilters = ReturnType<typeof useHomesFilters>;
