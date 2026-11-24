"use client";

import { useState, useSyncExternalStore } from "react";
import {
  clearRecentSearches,
  recentSearchCount,
  recentSearchSaving,
  setRecentSearchSaving,
  subscribeRecent,
} from "@/features/search/recent";
import { Toggle } from "@/shared/ui/Toggle";

export function RecentSearchSetting() {
  const saving = useSyncExternalStore(subscribeRecent, recentSearchSaving, () => true);
  const count = useSyncExternalStore(subscribeRecent, recentSearchCount, () => 0);
  const [message, setMessage] = useState("");

  return (
    <div className="border-line-soft flex flex-col gap-[8px] border-t pt-[12px]">
      <div className="flex items-center justify-between gap-[12px]">
        <div className="flex flex-col gap-[3px]">
          <span className="text-[15px] font-bold">최근 검색어 저장</span>
          <p className="text-text-sub text-[13px]">
            이 브라우저에 최대 8개를 30일간 보관해요. 끄면 기존 검색어도 지워요.
          </p>
        </div>
        <Toggle
          checked={saving}
          label="최근 검색어 저장"
          onChange={(enabled) => {
            setRecentSearchSaving(enabled);
            setMessage(
              enabled ? "최근 검색어 저장을 켰어요." : "최근 검색어 저장을 끄고 기록을 지웠어요.",
            );
          }}
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-[8px]">
        <span className="text-text-sub text-[13px]">저장된 검색어 {count}개</span>
        <button
          type="button"
          className="rounded-control border-line min-h-[44px] border px-[12px] text-[14px] font-bold disabled:opacity-50"
          disabled={count === 0}
          onClick={() => {
            clearRecentSearches();
            setMessage("최근 검색어를 지웠어요.");
          }}
        >
          최근 검색어 지우기
        </button>
      </div>
      {message && (
        <p role="status" className="text-brand-strong text-[13px]">
          {message}
        </p>
      )}
    </div>
  );
}
