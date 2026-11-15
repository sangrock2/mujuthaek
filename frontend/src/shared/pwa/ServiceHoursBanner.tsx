"use client";

import { useOffline } from "next/offline";
import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { API_BASE_URL } from "@/shared/lib/api/client";
import { endpoints } from "@/shared/lib/api/endpoints";
import { backendStatus, useBackendDown } from "@/shared/lib/api/availability";

/** 연결 실패를 알리고, 서버가 회복되면 실패한 조회를 다시 불러와요. */
export function ServiceHoursBanner() {
  const down = useBackendDown();
  const isOffline = useOffline();
  const client = useQueryClient();
  useEffect(() => {
    if (!down || isOffline) return;
    let stopped = false;
    let pending: AbortController | null = null;
    async function check() {
      if (stopped || pending || document.visibilityState === "hidden") return;
      const controller = new AbortController();
      pending = controller;
      const timeout = window.setTimeout(() => controller.abort(), 5000);
      try {
        const response = await fetch(`${API_BASE_URL}${endpoints.regions}`, {
          cache: "no-store",
          credentials: "omit",
          signal: controller.signal,
          headers: { Accept: "application/json" },
        });
        if (
          !stopped &&
          response.ok &&
          response.headers.get("Content-Type")?.includes("application/json")
        ) {
          backendStatus.markUp();
          void client.invalidateQueries({ predicate: (query) => query.state.status === "error" });
        }
      } catch {
        // 연결이 돌아올 때까지 현재 안내를 유지해요.
      } finally {
        window.clearTimeout(timeout);
        if (pending === controller) pending = null;
      }
    }
    void check();
    const interval = window.setInterval(() => void check(), 10000);
    window.addEventListener("online", check);
    document.addEventListener("visibilitychange", check);
    return () => {
      stopped = true;
      pending?.abort();
      window.clearInterval(interval);
      window.removeEventListener("online", check);
      document.removeEventListener("visibilitychange", check);
    };
  }, [down, isOffline, client]);
  if (!down || isOffline) return null;

  return (
    <div className="fixed inset-x-0 top-[12px] z-50 flex justify-center px-[16px]">
      <section
        role="status"
        className="bg-text shadow-float flex w-full max-w-[560px] items-center gap-[10px] rounded-[18px] px-[16px] py-[14px] text-white"
      >
        <span className="flex-1 text-[14px] leading-[1.5] font-semibold">
          서버에 일시적으로 연결하지 못했어요. 연결이 복구되면 자동으로 다시 불러와요.
        </span>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="text-brand-deep-text-2 min-h-[44px] cursor-pointer border-0 bg-transparent px-[6px] text-[14px] font-extrabold"
        >
          다시 시도
        </button>
      </section>
    </div>
  );
}
