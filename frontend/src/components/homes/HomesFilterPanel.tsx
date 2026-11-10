"use client";

import { filterGroups, moveInModes, sortOptions, type SortOption } from "@/features/homes/filters";
import type { HomesFilters } from "@/features/homes/useHomesFilters";
import { cn } from "@/lib/cn";

/** 입주 방식 · (모바일) 정렬 · 유형 · 내 판정 · 필터 초기화. 웹 왼쪽 칸과 모바일 필터 시트가 같이 써요 */
export function HomesFilterPanel({
  filters,
  onReset,
  withSort,
}: {
  filters: HomesFilters;
  /** 필터 초기화 (지역까지 처음으로) */
  onReset: () => void;
  /** 정렬도 여기서 고르기 (모바일. 웹은 목록 위에 따로 있어요) */
  withSort?: boolean;
}) {
  const groups = filterGroups.filter(
    // 유형은 임대 유형이라 빌려서 들어가기에서만 보여요
    (g) => g.key !== "type" || filters.mode === "빌려서 들어가기",
  );
  return (
    <>
      <div
        role="group"
        aria-label="입주 방식"
        className="bg-fill grid grid-cols-2 rounded-sm p-[4px]"
      >
        {moveInModes.map((m) => {
          const on = m === filters.mode;
          return (
            <button
              key={m}
              type="button"
              aria-pressed={on}
              onClick={() => filters.setMode(m)}
              className={cn(
                "min-h-[40px] cursor-pointer rounded-[9px] border-0 text-[14px]",
                on
                  ? "bg-surface text-text shadow-seg font-bold"
                  : "text-text-sub bg-transparent font-semibold",
              )}
            >
              {m}
            </button>
          );
        })}
      </div>
      {withSort && (
        <label className="flex flex-col gap-[8px] text-[15px] font-extrabold">
          정렬
          <select
            value={filters.sort}
            onChange={(e) => filters.setSort(e.target.value as SortOption)}
            className="border-line bg-surface text-text min-h-[48px] rounded-sm border border-solid px-[12px] text-[15px] font-semibold"
          >
            {sortOptions.map((o) => (
              <option key={o}>{o}</option>
            ))}
          </select>
        </label>
      )}
      {groups.map((g) => (
        <fieldset key={g.key} className="m-0 flex flex-col gap-[4px] border-0 p-0">
          <legend className="mb-[8px] p-0 text-[15px] font-extrabold">{g.legend}</legend>
          {g.options.map((o) => (
            <label key={o.key} className="flex min-h-[40px] items-center gap-[10px] text-[15px]">
              <input
                type="checkbox"
                checked={filters.checked[o.key]}
                onChange={(e) => filters.toggle(o.key, e.target.checked)}
                className="m-0 size-[18px]"
              />
              {o.label}
            </label>
          ))}
        </fieldset>
      ))}
      <button
        type="button"
        onClick={onReset}
        className="bg-fill text-text-sub min-h-[44px] cursor-pointer rounded-sm border-0 text-[14px] font-bold"
      >
        필터 초기화
      </button>
    </>
  );
}
