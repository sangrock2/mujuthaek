import Link from "next/link";
import { Building, House } from "lucide-react";
import { verdictLabel, type Verdict } from "@/components/ui/Badge";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";

export type NearMiss = { id: string; name: string; change: string; verdict: Verdict };

type NoMatchProps = {
  /** 아직 확인 못 한 조건 수 */
  missingCount: number;
  /** 조금만 달라지면 지원할 수 있는 곳 */
  nearMisses: NearMiss[];
  /** '새 공고 알림 받기' (PC) */
  onSubscribe?: () => void;
};

/** 1 · 내 집 · 지원 가능한 공고가 없을 때 (PC) */
export function WebNoMatchState({ missingCount, nearMisses, onSubscribe }: NoMatchProps) {
  return (
    <div className="bg-bg rounded-card-lg flex flex-col items-center gap-[18px] px-[32px] py-[56px] text-center">
      <span className="bg-surface text-brand flex size-[80px] items-center justify-center rounded-[26px]">
        <House size={40} strokeWidth={1.6} aria-hidden />
      </span>
      <h2 className="tracking-h1 m-0 text-[26px] font-extrabold">
        지금 조건으로 지원할 수 있는 공고가 없어요
      </h2>
      <span className="text-text-sub max-w-[520px] text-[16px] leading-[1.6]">
        아직 확인 못 한 조건이 {missingCount}개 있어요. 입력하면 결과가 달라질 수 있어요. 새 공고가
        나오면 바로 알려드릴게요.
      </span>
      <div className="flex flex-wrap justify-center gap-[8px]">
        <Link
          href={routes.profile}
          className="rounded-control bg-brand inline-flex min-h-[52px] items-center px-[22px] text-[16px] font-extrabold text-white no-underline hover:text-white"
        >
          확인 필요한 조건 입력하기
        </Link>
        <button
          type="button"
          onClick={onSubscribe}
          className="rounded-control bg-surface text-text min-h-[52px] cursor-pointer border-0 px-[20px] text-[16px] font-bold"
        >
          새 공고 알림 받기
        </button>
      </div>
      {nearMisses.length > 0 && (
        <div className="bg-surface flex w-full max-w-[600px] flex-col gap-[10px] rounded-[20px] px-[20px] py-[18px] text-left">
          <span className="text-[15px] font-extrabold">조금만 달라지면 지원할 수 있는 곳</span>
          {nearMisses.map((n) => (
            <Link
              key={n.id}
              href={routes.notice(n.id)}
              className="text-text hover:text-text flex min-h-[44px] items-center justify-between gap-[10px] no-underline"
            >
              <span className="text-[15px]">
                {n.name} · {n.change}
              </span>
              <span
                className={cn(
                  "text-[14px] font-bold",
                  n.verdict === "ok" ? "text-ok-text" : "text-check-text",
                )}
              >
                {verdictLabel[n.verdict]}
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

/** 1 · 내 집 · 지원 가능한 공고가 없을 때 (모바일) */
export function MNoMatchState({ missingCount, nearMisses }: NoMatchProps) {
  return (
    <section className="rounded-card bg-surface flex flex-col items-center gap-[12px] px-[20px] py-[28px] text-center">
      <span className="bg-fill text-placeholder-icon flex size-[64px] items-center justify-center rounded-[20px]">
        <Building size={32} aria-hidden />
      </span>
      <h2 className="tracking-title m-0 text-[20px] font-extrabold">
        지금 조건으로 지원할 수 있는
        <br />
        공고가 없어요
      </h2>
      <span className="text-text-sub text-[15px] leading-[1.6]">
        확인 못 한 조건이 {missingCount}개 있어요. 입력하면 결과가 달라질 수 있어요.
      </span>
      <Link
        href={routes.profile}
        className="rounded-control bg-brand flex min-h-[52px] items-center justify-center self-stretch text-[16px] font-extrabold text-white no-underline hover:text-white"
      >
        확인 필요한 조건 입력하기
      </Link>
      <Link
        href={routes.alerts}
        className="rounded-control bg-fill text-text hover:text-text flex min-h-[52px] items-center justify-center self-stretch text-[15px] font-bold no-underline"
      >
        새 공고 알림 받기
      </Link>
      {nearMisses.length > 0 && (
        <div className="border-line-soft flex flex-col gap-[8px] self-stretch border-t border-solid pt-[14px] text-left">
          <span className="text-[14px] font-extrabold">조금만 달라지면 지원할 수 있는 곳</span>
          {nearMisses.map((n) => (
            <span key={n.id} className="text-text-sub text-[14px]">
              {n.name} · {n.change} {verdictLabel[n.verdict]}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}
