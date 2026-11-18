"use client";

import { useState } from "react";
import { PersonalizationSummary } from "@/features/conditions/components/PersonalizationSummary";
import { BenefitEmptyState } from "../components/BenefitEmptyState";
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
  const data = useBenefits();
  const [cat, setCat] = useState<CatFilter>("전체");

  const shown = cat === "전체" ? data.items : data.items.filter((b) => b.cat === cat);
  const cats: CatFilter[] = ["전체", ...benefitCategories];

  return (
    <MPage>
      <MTopBar mode="home" />
      <main
        id="main-content"
        tabIndex={-1}
        className="flex flex-1 flex-col gap-[14px] px-[16px] pt-[20px] pb-[28px]"
      >
        <div className="flex flex-col gap-[4px] px-[4px]">
          <h1 className="tracking-h1 m-0 text-[26px] font-extrabold">내 혜택</h1>
          <span className="text-text-sub text-[15px]">
            <PersonalizationSummary
              kind="benefits"
              loading={data.loading}
              error={data.error}
              eligible={data.total}
            />
          </span>
        </div>
        <div
          role="group"
          aria-label="분야"
          className="flex gap-[6px] overflow-x-auto px-[4px] pb-[2px]"
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
                  on ? "bg-text text-white" : "bg-surface text-text-sub",
                )}
              >
                {c} {count}
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
        {!data.loading && !data.error && shown.length === 0 && (
          <BenefitEmptyState filtered={cat !== "전체"} onReset={() => setCat("전체")} />
        )}
        {shown.map((b) => (
          <Link
            key={b.id}
            href={routes.benefit(b.id)}
            className="bg-surface text-text hover:text-text flex flex-col gap-[8px] rounded-[22px] p-[18px] no-underline"
          >
            <span className="flex items-center justify-between gap-[8px]">
              <span className="text-text-tertiary text-[13px]">
                {b.cat} · {b.orgShort}
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
        {data.hasMore && (
          <button
            type="button"
            onClick={data.loadMore}
            disabled={data.loadingMore}
            className="bg-surface text-text min-h-[48px] cursor-pointer rounded-[18px] border-0 text-[15px] font-bold disabled:opacity-60"
          >
            {data.loadingMore ? "불러오는 중" : "더 보기"}
          </button>
        )}
        <span className="text-text-sub px-[4px] pt-[4px] text-[13px] leading-[1.6]">
          혜택 정보는 각 기관 공고를 정리한 거예요. 신청 전에 정책 원문을 꼭 확인해 주세요
        </span>
      </main>
      <MTabBar mode="home" current={routes.benefits} />
    </MPage>
  );
}
