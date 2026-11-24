"use client";

import { useState } from "react";
import { BenefitEmptyState } from "../components/BenefitEmptyState";
import { InfiniteScroll } from "@/shared/ui/InfiniteScroll";
import { QueryFeedback } from "@/shared/states/QueryFeedback";
import Link from "next/link";
import { MTabBar } from "@/shared/layout/MTabBar";
import { MTopBar } from "@/shared/layout/MTopBar";
import { MPage } from "@/shared/layout/Responsive";
import { VerdictBadge } from "@/shared/ui/Badge";
import { useBenefits } from "@/features/benefits/queries";
import { cn } from "@/shared/lib/cn";
import { routes } from "@/shared/lib/routes";
import { benefitCategories, type BenefitCategory } from "@/features/benefits/mocks/benefits";

type CatFilter = "전체" | BenefitCategory;

export function MBenefits() {
  const [cat, setCat] = useState<CatFilter>("전체");
  const data = useBenefits(cat === "전체" ? undefined : cat);

  const cats: CatFilter[] = ["전체", ...benefitCategories];

  return (
    <MPage className="stitch-surface">
      <MTopBar mode="home" />
      <main
        id="main-content"
        tabIndex={-1}
        className="flex flex-1 flex-col gap-[14px] px-[16px] pt-[20px] pb-[28px]"
      >
        <div className="flex flex-col gap-[4px] px-[4px]">
          <h1 className="tracking-h1 m-0 text-[26px] font-extrabold">내 혜택</h1>
        </div>
        <div
          role="group"
          aria-label="분야"
          className="bg-bg sticky top-[56px] z-[1] flex gap-[6px] overflow-x-auto px-[4px] py-2"
        >
          {cats.map((c) => {
            const count = c === "전체" ? data.total : data.counts[c];
            const on = c === cat;
            return (
              <button
                key={c}
                type="button"
                aria-pressed={on}
                onClick={() => setCat(c)}
                className={cn(
                  "rounded-pill min-h-[40px] flex-none cursor-pointer border-0 px-[14px] text-[14px] font-bold",
                  on ? "bg-brand text-white" : "bg-surface text-text-sub",
                )}
              >
                {c}
                {!data.loading && !data.error && ` ${count}`}
              </button>
            );
          })}
        </div>
        {data.yearlyAmount !== "–" && (
          <div className="bg-surface flex items-baseline justify-between rounded-[22px] px-[18px] py-[16px]">
            <span className="text-text-sub text-[14px]">1년에 받을 수 있는 돈</span>
            <span className="tracking-title text-[22px] font-extrabold">{data.yearlyAmount}</span>
          </div>
        )}
        {(data.loading || data.error) && (
          <QueryFeedback error={data.error} label="혜택" queryKey={["benefits"]} />
        )}
        {!data.loading && !data.error && !data.hasMore && data.items.length === 0 && (
          <BenefitEmptyState filtered={cat !== "전체"} onReset={() => setCat("전체")} />
        )}
        {!data.loading && !data.error && (
          <div className="flex items-center justify-between gap-2 px-1">
            <h2 className="m-0 text-base font-extrabold">혜택 목록</h2>
            <span className="text-text-sub text-sm tabular-nums">
              전체 {(cat === "전체" ? data.total : data.counts[cat]).toLocaleString("ko-KR")}건
            </span>
          </div>
        )}
        {data.items.map((b, index) => (
          <Link
            key={b.id}
            href={routes.benefit(b.id)}
            className="bg-surface text-text hover:text-text flex flex-col gap-[8px] rounded-[22px] p-[18px] no-underline"
          >
            <span className="flex items-center justify-between gap-[8px]">
              <span className="text-text-tertiary text-[13px]">
                {index + 1}. {b.cat} · {b.orgShort}
              </span>
              <span className="text-text-sub text-[13px] font-extrabold">{b.dday}</span>
            </span>
            <span className="tracking-title text-[18px] font-extrabold">{b.title}</span>
            <span className="flex items-center justify-between gap-[8px]">
              <span className="text-[15px] font-semibold">{b.amountShort}</span>
              <VerdictBadge verdict={b.verdict} size="md" className="flex-none text-[12px]" />
            </span>
          </Link>
        ))}
        <InfiniteScroll data={data} label="혜택" />
      </main>
      <MTabBar mode="home" current={routes.benefits} />
    </MPage>
  );
}
