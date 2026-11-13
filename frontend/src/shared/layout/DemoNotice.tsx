"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";
import { Info, X } from "lucide-react";
import { USE_MOCKS } from "@/shared/lib/api/config";
import { routes } from "@/shared/lib/routes";

const KEY = "mujuthaek:demo-notice-hidden";
const EVENT = "mujuthaek:demo-notice";

function readHidden() {
  try {
    return window.sessionStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

function subscribe(listener: () => void) {
  window.addEventListener(EVENT, listener);
  return () => window.removeEventListener(EVENT, listener);
}

function hide() {
  try {
    window.sessionStorage.setItem(KEY, "1");
  } catch {
    // 저장하지 못해도 이번 화면에서는 닫아요
  }
  window.dispatchEvent(new Event(EVENT));
}

/**
 * 목업(시연) 모드에서만 화면 맨 위에 「예시 데이터로 보여 주는 시연 화면」이라고 알려요. 실제 API 모드에서는 아무것도 그리지 않아요.
 * 닫으면 이 탭에서는 다시 보이지 않아요(sessionStorage). 서버 렌더와 첫 화면은 보이는 상태라 자리가 밀리지 않아요
 */
export function DemoNotice() {
  if (!USE_MOCKS) return null;
  return <DemoNoticeBar />;
}

function DemoNoticeBar() {
  const hidden = useSyncExternalStore(subscribe, readHidden, () => false);
  if (hidden) return null;
  return (
    <div
      role="note"
      className="bg-brand-soft text-brand-strong flex min-h-[36px] w-full items-center justify-center gap-[6px] px-[16px] text-[13px] font-semibold"
    >
      <Info size={15} aria-hidden className="flex-none" />
      <span className="min-w-0">예시 데이터로 보여 주는 시연 화면이에요</span>
      <Link
        href={routes.howItWorks}
        className="text-brand-strong hover:text-brand-strong flex-none underline max-[479px]:hidden"
      >
        어떻게 만들었나요
      </Link>
      <button
        type="button"
        onClick={hide}
        aria-label="시연 안내 닫기"
        className="text-brand-strong -mr-[8px] inline-flex size-[36px] flex-none cursor-pointer items-center justify-center border-0 bg-transparent p-0"
      >
        <X size={15} aria-hidden />
      </button>
    </div>
  );
}
