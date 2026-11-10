"use client";

import { useOffline } from "next/offline";
import { OfflineNotice } from "@/components/states/OfflineNotice";

/** 인터넷이 끊기면 화면 위에 떠서 알려줘요 (디자인 MStates 4 · 오프라인) */
export function OfflineBanner() {
  const isOffline = useOffline();
  if (!isOffline) return null;

  return (
    <div className="fixed inset-x-0 top-[12px] z-50 flex justify-center px-[16px]">
      <OfflineNotice
        onReconnect={() => window.location.reload()}
        className="shadow-float w-full max-w-[560px]"
      />
    </div>
  );
}
