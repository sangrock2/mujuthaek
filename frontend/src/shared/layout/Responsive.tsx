"use client";

import { useSyncExternalStore } from "react";
import { cn } from "@/shared/lib/cn";

const query = "(min-width: 1024px)";
const subscribe = (notify: () => void) => {
  const media = window.matchMedia(query);
  media.addEventListener("change", notify);
  return () => media.removeEventListener("change", notify);
};
const viewport = () => window.matchMedia(query).matches;
const serverViewport = () => undefined;

/** PC(Web*) / 모바일(M*) 화면을 따로 그리고 폭에 따라 하나만 보여줘요 */
export function Responsive({ web, mobile }: { web: React.ReactNode; mobile: React.ReactNode }) {
  const desktop = useSyncExternalStore(subscribe, viewport, serverViewport);
  if (desktop === undefined) {
    return (
      <div aria-label="화면을 준비하는 중" aria-busy="true" className="bg-bg min-h-screen flex-1" />
    );
  }
  return <div className="flex min-h-full flex-1 flex-col">{desktop ? web : mobile}</div>;
}

/** PC 화면 바탕: 회색 페이지 + 본문 최대 1200px */
export function WebPage({ children }: { children: React.ReactNode }) {
  return <div className="bg-bg text-text flex min-h-screen w-full flex-col">{children}</div>;
}

export function WebMain({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <main
      id="main-content"
      tabIndex={-1}
      className={cn(
        "mx-auto box-border flex w-full max-w-[1200px] flex-1 flex-col gap-[24px] px-[32px] pt-[40px] pb-[72px]",
        className,
      )}
    >
      {children}
    </main>
  );
}

/** 모바일 화면 바탕 */
export function MPage({ children }: { children: React.ReactNode }) {
  return <div className="bg-bg text-text flex min-h-screen w-full flex-col">{children}</div>;
}
