"use client";

import Link from "next/link";
import { Banknote, Info, MapPin, Percent, Wallet, type LucideIcon } from "lucide-react";
import { WebHeader } from "@/components/layout/WebHeader";
import { WebMain, WebPage } from "@/components/layout/Responsive";
import { useRegionScope, useSupportList } from "@/features/business/queries";
import { useTypeFilter } from "@/features/business/state";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import type { SupportType } from "@/mocks/business";
import { RegionScopeChips, SupportBadge, TypeFilters, supportFilters } from "./parts";

const typeIcon: Record<SupportType, LucideIcon> = { fund: Wallet, loan: Banknote, tax: Percent };
const typeTone: Record<SupportType, string> = {
  fund: "bg-brand-soft text-brand",
  loan: "bg-placeholder-bg text-text-sub",
  tax: "bg-placeholder-bg text-text-sub",
};

const cols = "grid gap-[24px] px-[28px]";
const colTemplate = {
  gridTemplateColumns: "minmax(0, 3fr) minmax(0, 3fr) minmax(0, 2.2fr) minmax(0, 1fr)",
};

export function WebBizSupport() {
  const scope = useRegionScope();
  const { data, loading } = useSupportList(scope);
  const { filter, setFilter, count, visible } = useTypeFilter(data.items);

  return (
    <WebPage>
      <WebHeader mode="business" current={routes.bizSupport} />
      <WebMain>
        <div className="flex flex-wrap items-end justify-between gap-[16px]">
          <div className="flex flex-col gap-[6px]">
            <h1 className="tracking-h1 m-0 text-[32px] font-extrabold">사업 지원</h1>
            <span className="text-text-sub text-[16px]">
              내 사업 조건으로 받을 수 있는 지원{" "}
              <strong className="text-brand-strong">{data.count}개</strong> · {data.baseDate} 기준
            </span>
          </div>
          <div className="flex flex-col items-end gap-[8px]">
            <RegionScopeChips scope={scope} />
            <TypeFilters
              label="지원 종류"
              options={supportFilters(false)}
              value={filter}
              onChange={setFilter}
              count={count}
              className="flex-wrap"
            />
          </div>
        </div>

        {Boolean(data.missingSiteCount) && (
          <section
            aria-label="판정 보완"
            className="rounded-card bg-surface flex flex-wrap items-center gap-x-[16px] gap-y-[12px] px-[22px] py-[18px]"
          >
            <span className="bg-check-bg text-check-text flex size-[40px] flex-none items-center justify-center rounded-sm">
              <MapPin size={20} aria-hidden />
            </span>
            <span className="flex flex-col gap-[2px]" style={{ flex: "1 1 280px" }}>
              <span className="text-[16px] font-extrabold">
                사업장 소재지를 알려주면 {data.missingSiteCount}개를 더 판정할 수 있어요
              </span>
              <span className="text-text-sub text-[14px]">
                지역 지원금은 사업장이 어디인지에 따라 대상이 달라요
              </span>
            </span>
            <Link
              href={routes.bizOnboarding}
              className="bg-brand inline-flex min-h-[44px] items-center rounded-sm px-[18px] text-[15px] font-bold text-white no-underline hover:text-white"
            >
              입력하기
            </Link>
          </section>
        )}

        <section aria-label="사업 지원 목록" className="rounded-card-lg bg-surface overflow-hidden">
          <div className="overflow-x-auto">
            <div className="min-w-[760px]" role="table" aria-label="사업 지원 목록">
              <div
                role="row"
                className={cn(
                  cols,
                  "border-line text-text-sub border-b border-solid py-[16px] text-[13px] font-bold",
                )}
                style={colTemplate}
              >
                <span role="columnheader">지원</span>
                <span role="columnheader">내용</span>
                <span role="columnheader">내 판정</span>
                <span role="columnheader" className="text-right">
                  기한
                </span>
              </div>
              {visible.length === 0 && (
                <p className="text-text-sub m-0 px-[28px] py-[48px] text-center text-[15px]">
                  {loading
                    ? "사업 지원을 불러오는 중이에요"
                    : "지금 받을 수 있는 사업 지원이 없어요"}
                </p>
              )}
              {visible.map((it) => {
                const Icon = typeIcon[it.type];
                return (
                  <div
                    key={it.id}
                    role="row"
                    className={cn(
                      cols,
                      "border-line-soft items-center border-b border-solid py-[22px]",
                    )}
                    style={colTemplate}
                  >
                    <span role="cell" className="flex items-center gap-[14px]">
                      <span
                        className={cn(
                          "rounded-control flex size-[44px] flex-none items-center justify-center",
                          typeTone[it.type],
                        )}
                      >
                        <Icon size={22} aria-hidden />
                      </span>
                      <span className="flex min-w-0 flex-col gap-[4px]">
                        {it.href ? (
                          <Link
                            href={it.href}
                            className="text-text hover:text-text text-[17px] font-extrabold tracking-[-0.02em] no-underline"
                          >
                            {it.title}
                          </Link>
                        ) : (
                          <span className="text-[17px] font-extrabold tracking-[-0.02em]">
                            {it.title}
                          </span>
                        )}
                        <span className="text-text-sub text-[13px]">{it.org}</span>
                      </span>
                    </span>
                    <span role="cell" className="flex flex-col gap-[4px]">
                      <span className="text-[15px] font-semibold">{it.body}</span>
                      <span className="text-text-sub text-[13px]">{it.note}</span>
                    </span>
                    <span role="cell" className="flex flex-col items-start gap-[6px]">
                      <SupportBadge status={it.status} size="md" className="px-[10px]" />
                      <span className="text-text-sub text-[13px]">{it.reason}</span>
                    </span>
                    <span role="cell" className="text-right text-[15px] font-extrabold">
                      {it.due}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        <p className="text-text-sub m-0 flex items-start gap-[8px] text-[14px] leading-[1.6]">
          <Info size={18} className="mt-[2px] flex-none" aria-hidden />
          세금 정보는 참고용이에요. 최종 판단은 세무서나 세무사에게 확인해주세요.
        </p>
      </WebMain>
    </WebPage>
  );
}
