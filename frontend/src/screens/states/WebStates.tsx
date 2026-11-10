"use client";

import { WebLoadErrorState } from "@/components/states/LoadErrorState";
import { WebNoMatchState } from "@/components/states/NoMatchState";
import { WebNotFoundState } from "@/components/states/NotFoundState";
import { useStatesPreview } from "@/features/content/queries";

function Case({
  label,
  title,
  children,
}: {
  label: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section aria-label={label} className="flex flex-col gap-[10px]">
      <span className="text-text-sub text-[14px] font-extrabold">{title}</span>
      {children}
    </section>
  );
}

/** 빈 상태 · 오류 미리보기 (개발용, 디자인 WebStates 캔버스) */
export function WebStates() {
  const { data } = useStatesPreview();

  return (
    <div className="bg-placeholder-bg text-text min-h-screen w-full">
      <main className="mx-auto box-border flex w-full max-w-[1200px] flex-col gap-[28px] px-[32px] pt-[48px] pb-[72px]">
        <div className="flex flex-col gap-[6px]">
          <h1 className="tracking-h1 m-0 text-[30px] font-extrabold">빈 상태 · 오류</h1>
          <span className="text-text-sub text-[16px]">
            결과가 없거나 문제가 생겼을 때 화면 가운데 영역에 들어가는 모습이에요. 막다른 길이 되지
            않게 항상 다음 행동을 같이 보여줘요
          </span>
        </div>
        <Case label="결과 0곳" title="1 · 내 집 · 지원 가능한 공고가 없을 때">
          <WebNoMatchState missingCount={data.missingCount} nearMisses={data.nearMisses} />
        </Case>
        <Case label="불러오기 실패" title="2 · 데이터를 불러오지 못했을 때">
          <WebLoadErrorState code={data.error.code} at={data.error.at} onRetry={() => {}} />
        </Case>
        <Case label="없는 페이지" title="3 · 없는 페이지 (404)">
          <WebNotFoundState />
        </Case>
      </main>
    </div>
  );
}
