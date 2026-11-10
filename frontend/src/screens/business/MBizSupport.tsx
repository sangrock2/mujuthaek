"use client";

import Link from "next/link";
import { ChevronRight, MapPin } from "lucide-react";
import { MTabBar } from "@/components/layout/MTabBar";
import { MTopBar } from "@/components/layout/MTopBar";
import { MPage } from "@/components/layout/Responsive";
import { useRegionScope, useSupportList } from "@/features/business/queries";
import { useTypeFilter } from "@/features/business/state";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import { RegionScopeChips, SupportBadge, TypeFilters, supportFilters } from "./parts";

export function MBizSupport() {
  const scope = useRegionScope();
  const { data, loading } = useSupportList(scope);
  const { filter, setFilter, count, visible } = useTypeFilter(data.items);

  return (
    <MPage>
      <MTopBar mode="business" />
      <main className="flex flex-1 flex-col gap-[12px] px-[16px] pt-[20px] pb-[28px]">
        <div className="flex flex-col gap-[4px] px-[4px]">
          <h1 className="tracking-h1 m-0 text-[26px] font-extrabold">사업 지원</h1>
          <span className="text-text-sub text-[15px]">
            받을 수 있는 지원 <strong className="text-brand-strong">{data.count}개</strong> ·{" "}
            {data.baseDate} 기준
          </span>
        </div>

        <RegionScopeChips scope={scope} className="px-[4px]" />

        <TypeFilters
          label="지원 종류"
          options={supportFilters(true)}
          value={filter}
          onChange={setFilter}
          count={count}
          mobile
          className="overflow-x-auto px-[4px] pb-[2px]"
        />

        {Boolean(data.missingSiteCount) && (
          <Link
            href={routes.bizOnboarding}
            className="bg-surface text-text hover:text-text flex items-center gap-[12px] rounded-[22px] p-[16px] no-underline"
          >
            <span className="bg-check-bg text-check-text flex size-[40px] flex-none items-center justify-center rounded-sm">
              <MapPin size={20} aria-hidden />
            </span>
            <span className="flex flex-1 flex-col gap-[2px]">
              <span className="text-[15px] font-extrabold">사업장 소재지를 알려주세요</span>
              <span className="text-text-sub text-[13px]">
                {data.missingSiteCount}개를 더 판정할 수 있어요
              </span>
            </span>
            <ChevronRight size={18} className="text-text-tertiary" aria-hidden />
          </Link>
        )}

        {visible.length === 0 && (
          <p className="text-text-sub m-0 px-[20px] py-[40px] text-center text-[15px]">
            {loading ? "사업 지원을 불러오는 중이에요" : "지금 받을 수 있는 사업 지원이 없어요"}
          </p>
        )}

        {visible.map((it) => {
          const body = (
            <>
              <span className="flex items-center justify-between gap-[8px]">
                <SupportBadge status={it.status} size="xs" className="px-[8px] py-[3px]" />
                <span className="text-[13px] font-extrabold">{it.due}</span>
              </span>
              <h2 className="tracking-title m-0 text-[18px] font-extrabold">{it.title}</h2>
              <span className="text-text-tertiary text-[12px]">{it.mOrg}</span>
              <span className="text-[15px] font-semibold">{it.mBody}</span>
              {it.note && <span className="text-text-sub text-[13px]">{it.note}</span>}
              <span className="border-line-soft text-text-sub border-t border-solid pt-[8px] text-[13px]">
                {it.mReason}
              </span>
            </>
          );
          const box = "bg-surface text-text flex flex-col gap-[8px] rounded-[22px] p-[18px]";
          // 상세 주소가 없는 지원은 눌러도 갈 곳이 없어서 글로만 보여요 (웹과 같아요)
          return it.href ? (
            <Link key={it.id} href={it.href} className={cn(box, "hover:text-text no-underline")}>
              {body}
            </Link>
          ) : (
            <div key={it.id} className={box}>
              {body}
            </div>
          );
        })}

        <span className="text-text-sub px-[4px] text-[13px] leading-[1.6]">
          세금 정보는 참고용이에요. 최종 판단은 세무서나 세무사에게 확인해주세요.
        </span>
      </main>
      <MTabBar mode="business" current={routes.bizSupport} />
    </MPage>
  );
}
