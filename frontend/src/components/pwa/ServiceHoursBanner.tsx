"use client";

import { useOffline } from "next/offline";
import { SERVICE_HOURS, useBackendDown } from "@/lib/api/availability";

/** 백엔드가 응답하지 않으면 화면 위에 떠서 운영 시간을 알려줘요. 인터넷이 끊긴 때는 오프라인 안내가 먼저예요 */
export function ServiceHoursBanner() {
  const down = useBackendDown();
  const isOffline = useOffline();
  if (!down || isOffline) return null;

  return (
    <div className="fixed inset-x-0 top-[12px] z-50 flex justify-center px-[16px]">
      <section
        role="status"
        className="bg-text shadow-float flex w-full max-w-[560px] items-center gap-[10px] rounded-[18px] px-[16px] py-[14px] text-white"
      >
        <span className="flex-1 text-[14px] leading-[1.5] font-semibold">
          서버에 연결하지 못했어요 · 서비스 운영 시간: {SERVICE_HOURS}
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
