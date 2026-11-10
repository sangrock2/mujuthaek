"use client";

import { useState } from "react";
import Link from "next/link";
import { MTabBar } from "@/components/layout/MTabBar";
import { MTopBar } from "@/components/layout/MTopBar";
import { MPage } from "@/components/layout/Responsive";
import { VerdictBadge } from "@/components/ui/Badge";
import { useBenefits } from "@/features/benefits/queries";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import { benefitCategories, type BenefitCategory } from "@/mocks/benefits";

type CatFilter = "전체" | BenefitCategory;

export function MBenefits() {
  const data = useBenefits();
  const [cat, setCat] = useState<CatFilter>("전체");

  const shown = cat === "전체" ? data.items : data.items.filter((b) => b.cat === cat);
  const cats: CatFilter[] = ["전체", ...benefitCategories];

  return (
    <MPage>
      <MTopBar mode="home" />
      <main className="flex flex-1 flex-col gap-[14px] px-[16px] pt-[20px] pb-[28px]">
        <div className="flex flex-col gap-[4px] px-[4px]">
          <h1 className="tracking-h1 m-0 text-[26px] font-extrabold">내 혜택</h1>
          <span className="text-text-sub text-[15px]">
            받을 수 있는 혜택 <strong className="text-brand-strong">{data.total}개</strong>
            {data.asOf && ` · ${data.asOf} 기준`}
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
        {data.loading && (
          <p className="text-text-sub m-0 px-[4px] py-[24px] text-center text-[15px]">
            내 조건으로 혜택을 판정하는 중이에요
          </p>
        )}
        {data.error && (
          <p role="alert" className="text-text-sub m-0 px-[4px] py-[24px] text-center text-[15px]">
            혜택을 불러오지 못했어요. 잠시 뒤 다시 시도해 주세요
          </p>
        )}
        {!data.loading && !data.error && shown.length === 0 && (
          <p className="text-text-sub m-0 px-[4px] py-[24px] text-center text-[15px]">
            지금 받을 수 있는 혜택이 없어요
          </p>
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
