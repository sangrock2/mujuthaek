import Link from "next/link";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import type { NoticeRankTier, NoticeRanking } from "@/mocks/notice";

function TierMark({ tier, mobile }: { tier: NoticeRankTier; mobile?: boolean }) {
  switch (tier.state) {
    case "mine":
      return (
        <span
          className={cn("text-brand-strong font-extrabold", mobile ? "text-[12px]" : "text-[13px]")}
        >
          내 순위
        </span>
      );
    case "no":
      return (
        <span className={cn("text-text-sub font-bold", mobile ? "text-[12px]" : "text-[13px]")}>
          해당 안 됨
        </span>
      );
    case "check":
      return (
        <Link
          href={routes.profile}
          className={cn(
            "bg-check-bg text-check-text hover:text-check-text inline-flex min-h-[36px] flex-none items-center rounded-[10px] px-[10px] font-bold no-underline",
            mobile ? "text-[12px]" : "text-[13px]",
          )}
        >
          확인 필요
        </Link>
      );
    default:
      return null;
  }
}

const dot = (mine: boolean) => (mine ? "bg-brand text-white" : "bg-check-off text-text-sub");

/** PC '내 순위' 칸: 깊은 초록 박스 + 순위 목록 + 뽑는 방법 */
export function WebRankCard({
  ranking,
  className,
}: {
  ranking: NoticeRanking;
  className?: string;
}) {
  return (
    <section
      aria-labelledby="rank-h"
      className={cn(
        "rounded-card-lg bg-surface flex flex-col gap-[14px] px-[26px] py-[24px]",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-[10px]">
        <h2 id="rank-h" className="tracking-title m-0 text-[20px] font-extrabold">
          내 순위
        </h2>
        <span className="text-text-sub text-[13px]">높은 순위부터 뽑아요</span>
      </div>
      <div className="bg-brand-deep flex items-center gap-[14px] rounded-[18px] px-[18px] py-[16px] text-white">
        <span className="tracking-h1 flex-none text-[30px] font-extrabold">
          {ranking.myRank}순위
        </span>
        <span className="text-brand-deep-text text-[14px] leading-[1.5]">{ranking.reason}</span>
      </div>
      <ol className="m-0 flex list-none flex-col gap-[6px] p-0">
        {ranking.tiers.map((t) => {
          const mine = t.state === "mine";
          return (
            <li
              key={t.rank}
              className={cn(
                "rounded-control flex items-center gap-[12px] px-[14px] py-[12px]",
                mine ? "bg-brand-soft" : "bg-bg",
              )}
            >
              <span
                className={cn(
                  "rounded-pill flex size-[28px] flex-none items-center justify-center text-[14px] font-extrabold",
                  dot(mine),
                )}
              >
                {t.rank}
              </span>
              <span className="flex flex-1 flex-col gap-[2px]">
                <span className="text-[15px] font-bold">{t.rank}순위</span>
                <span className="text-text-sub text-[13px]">{t.desc}</span>
              </span>
              <TierMark tier={t} />
            </li>
          );
        })}
      </ol>
      <span className="text-text-sub text-[13px]">
        같은 순위 안에서는 {ranking.tieBreak}으로 정해요 · 근거 원문 {ranking.sourcePage}쪽
      </span>
    </section>
  );
}

/** 모바일 '내 순위' 칸 */
export function MRankCard({ ranking }: { ranking: NoticeRanking }) {
  return (
    <section
      aria-labelledby="rank-h"
      className="rounded-card bg-surface mx-[16px] flex flex-col gap-[10px] px-[20px] py-[16px]"
    >
      <div className="flex items-center justify-between">
        <h3 id="rank-h" className="m-0 text-[17px] font-extrabold">
          내 순위
        </h3>
        <span className="text-text-sub text-[12px]">높은 순위부터 뽑아요</span>
      </div>
      <div className="bg-brand-deep rounded-tile flex items-center gap-[12px] px-[16px] py-[14px] text-white">
        <span className="tracking-h1 flex-none text-[26px] font-extrabold">
          {ranking.myRank}순위
        </span>
        <span className="text-brand-deep-text text-[13px] leading-[1.5]">{ranking.reason}</span>
      </div>
      <ol className="m-0 flex list-none flex-col gap-[6px] p-0">
        {ranking.tiers.map((t) => {
          const mine = t.state === "mine";
          return (
            <li
              key={t.rank}
              className={cn(
                "flex items-center gap-[10px] rounded-sm px-[12px]",
                t.state === "check" ? "py-[8px]" : "py-[10px]",
                mine ? "bg-brand-soft" : "bg-bg",
              )}
            >
              <span
                className={cn(
                  "rounded-pill flex size-[24px] flex-none items-center justify-center text-[13px] font-extrabold",
                  dot(mine),
                )}
              >
                {t.rank}
              </span>
              <span className={cn("flex-1 text-[14px]", !mine && "text-text-sub")}>{t.desc}</span>
              <TierMark tier={t} mobile />
            </li>
          );
        })}
      </ol>
      <span className="text-text-sub text-[12px]">
        같은 순위 안에서는 {ranking.tieBreak}으로 정해요 · 근거 원문 {ranking.sourcePage}쪽
      </span>
    </section>
  );
}
