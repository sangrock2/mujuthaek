"use client";

import { useState } from "react";
import { useConditions } from "@/features/conditions/store";
import { useRegions } from "@/features/regions/queries";
import type { Regions } from "@/lib/regions";
import type { HomeListing } from "@/mocks/homes";

const NATIONWIDE = "nationwide";

/** 필터 지역 중 하나에 들면 보여줘요. 전국 공고와 필터가 없을 때는 항상 */
export function matchesAnyRegion(item: HomeListing, codes: string[], regions: Regions) {
  return (
    codes.length === 0 ||
    item.region === NATIONWIDE ||
    codes.some((code) => regions.contains(code, item.region))
  );
}

export function listingRegionLabel(item: HomeListing, regions: Regions) {
  if (item.region === NATIONWIDE) return "전국";
  return item.regionName ?? regions.label(item.region);
}

/**
 * 지역 선택 상태 (지역 코드). 처음엔 내 조건의 찾아볼 지역(이사갈 곳)으로 보여주고, 없으면 전체예요.
 * 사는 곳으로는 거르지 않아요 (거주 요건 판정에만 써요). 시·도를 직접 고르면 그 지역으로 바꿔요
 */
export function useRegionFilter() {
  // null = 아직 안 고름 → 내 지역, "mine" = 내 지역 다시 고름, "" = 전체
  const [picked, setPicked] = useState<string | null>(null);
  const regions = useRegions();
  const stored = useConditions();
  const device = stored.status === "ready" ? stored.device : null;
  const mine = device?.searchRegionCodes ?? [];
  const selected = picked !== null && picked !== "mine" ? picked : null;
  const isMine = mine.length > 0 && selected === null;
  /** 시·도 · 시·군·구 칸에 보이는 코드. 내 지역을 보는 중이거나 전체면 "" */
  const code = selected ?? "";
  const codes = isMine ? mine : code ? [code] : [];

  return {
    code,
    /** 시·도를 고르면 그 시·도 전체, 시·군·구를 ""로 고르면 다시 시·도 전체 */
    pick: setPicked,
    reset: () => setPicked(""),
    /** 내 지역: 찾아볼 지역. 정하지 않았으면 빈 배열 */
    mine,
    /** 사는 곳 (배지로만 보여줘요). 모르면 "" */
    residence: device?.regionCode ?? "",
    pickMine: () => setPicked("mine"),
    isMine,
    isAll: codes.length === 0,
    /** 지금 보는 지역 코드들 (맞춤 목록 API의 filters.regionCodes) */
    codes,
    /** "부산 해운대구 · 부산 수영구" / "전체 지역" */
    label: codes.length ? codes.map(regions.label).join(" · ") : "전체 지역",
    matches: (item: HomeListing) => matchesAnyRegion(item, codes, regions),
    regionLabelOf: (item: HomeListing) => listingRegionLabel(item, regions),
  };
}

export type RegionFilter = ReturnType<typeof useRegionFilter>;
