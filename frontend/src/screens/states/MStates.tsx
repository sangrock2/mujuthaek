"use client";

import { MLoadErrorState } from "@/components/states/LoadErrorState";
import { MNoMatchState } from "@/components/states/NoMatchState";
import { MNotFoundState } from "@/components/states/NotFoundState";
import { OfflineNotice } from "@/components/states/OfflineNotice";
import { useStatesPreview } from "@/features/content/queries";
import { cn } from "@/lib/cn";

function Label({ first, children }: { first?: boolean; children: React.ReactNode }) {
  return (
    <span className={cn("text-text-sub px-[4px] text-[13px] font-bold", !first && "pt-[8px]")}>
      {children}
    </span>
  );
}

/** 빈 상태 · 오류 미리보기 (개발용, 디자인 MStates 캔버스) */
export function MStates() {
  const { data } = useStatesPreview();

  return (
    <div className="bg-bg text-text flex min-h-screen w-full flex-col">
      <main className="flex flex-1 flex-col gap-[14px] px-[16px] pt-[24px] pb-[32px]">
        <Label first>1 · 내 집 · 지원 가능한 공고가 없을 때</Label>
        <MNoMatchState missingCount={data.missingCount} nearMisses={data.nearMisses} />
        <Label>2 · 불러오지 못했을 때</Label>
        <MLoadErrorState code={data.error.code} at={data.error.at} onRetry={() => {}} />
        <Label>3 · 없는 페이지</Label>
        <MNotFoundState />
        <Label>4 · 오프라인</Label>
        <OfflineNotice />
      </main>
    </div>
  );
}
