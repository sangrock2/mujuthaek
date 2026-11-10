"use client";

import Link from "next/link";
import { ArrowRight, Briefcase, ChevronRight } from "lucide-react";
import { WebHeader } from "@/components/layout/WebHeader";
import { WebMain, WebPage } from "@/components/layout/Responsive";
import { VerdictBadge } from "@/components/ui/Badge";
import { InfoTag } from "@/components/ui/Chip";
import {
  useBizProfileChips,
  useBusinessSummary,
  useInitialSpaceType,
  useRegionScope,
  useSupportList,
} from "@/features/business/queries";
import { useTypeFilter } from "@/features/business/state";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import {
  RegionScopeChips,
  SupportBadge,
  TypeFilters,
  spaceFilters,
  spaceLink,
  SpaceTypeTag,
} from "./parts";

const ASIDE_SUPPORT_COUNT = 3;

export function WebBusiness() {
  const scope = useRegionScope();
  const { data, loading } = useBusinessSummary(scope);
  const profileChips = useBizProfileChips();
  const { data: support } = useSupportList(scope);
  const { filter, setFilter, count, visible } = useTypeFilter(data.list, useInitialSpaceType());
  const asideItems = support.items.slice(0, ASIDE_SUPPORT_COUNT);

  return (
    <WebPage>
      <WebHeader mode="business" current={routes.business} />
      <WebMain>
        <div className="flex flex-col gap-[6px]">
          <h1 className="tracking-h1 m-0 text-[32px] font-extrabold">사업공간</h1>
          <span className="text-text-sub text-[16px]">
            내 사업 조건으로 입주 지원할 수 있는 곳{" "}
            <strong className="text-brand-strong">{data.spaces.count}곳</strong>
          </span>
        </div>

        <section
          aria-label="내 사업 정보"
          className="rounded-card bg-surface flex flex-wrap items-center gap-[8px] px-[20px] py-[16px]"
        >
          <span className="mr-[6px] inline-flex items-center gap-[8px] text-[15px] font-extrabold">
            <Briefcase size={20} className="text-brand" aria-hidden />내 사업 정보
          </span>
          {profileChips.length === 0 && (
            <span className="text-text-sub text-[14px]">
              사업 정보를 넣으면 공간 · 지원을 내 조건으로 판정해요
            </span>
          )}
          {profileChips.map((c) => (
            <span
              key={c}
              className="rounded-pill bg-fill text-text px-[14px] py-[7px] text-[14px] font-semibold"
            >
              {c}
            </span>
          ))}
          <span className="flex-1" />
          <Link
            href={routes.bizOnboarding}
            className="text-brand-strong hover:text-brand-strong inline-flex min-h-[44px] items-center px-[8px] text-[14px] font-bold no-underline"
          >
            {profileChips.length ? "수정" : "입력하기"}
          </Link>
        </section>

        <section
          aria-label="요약"
          className="grid gap-[16px]"
          style={{ gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}
        >
          <a
            href="#spaces"
            className="rounded-card-lg bg-brand-deep flex items-end justify-between gap-[16px] px-[28px] py-[26px] text-white no-underline hover:text-white"
          >
            <span className="flex flex-col gap-[8px]">
              <span className="text-brand-deep-text text-[15px] font-semibold">
                입주 지원 가능 공간
              </span>
              <span className="tracking-h1 text-[40px] font-extrabold">{data.spaces.count}곳</span>
              <span className="text-brand-deep-text text-[14px]">
                마감 임박 {data.spaces.closingSoon}곳
                {data.spaces.newThisWeek !== undefined &&
                  ` · 이번 주 새로 올라온 공간 ${data.spaces.newThisWeek}곳`}
              </span>
            </span>
            <span className="rounded-pill flex size-[44px] flex-none items-center justify-center bg-white/12">
              <ArrowRight size={20} aria-hidden />
            </span>
          </a>
          <Link
            href={routes.bizSupport}
            className="rounded-card-lg bg-surface text-text hover:text-text flex items-end justify-between gap-[16px] px-[28px] py-[26px] no-underline"
          >
            <span className="flex flex-col gap-[8px]">
              <span className="text-text-sub text-[15px] font-semibold">
                받을 수 있는 사업 지원
              </span>
              <span className="tracking-h1 text-[40px] font-extrabold">{data.support.count}개</span>
              <span className="text-text-sub text-[14px]">
                {data.support.maxAmount && (
                  <>
                    지원금 최대{" "}
                    <strong className="text-brand-strong">{data.support.maxAmount}</strong> ·{" "}
                  </>
                )}
                확인 필요 {data.support.needCheck}개
              </span>
            </span>
            <span className="rounded-pill bg-fill text-text flex size-[44px] flex-none items-center justify-center">
              <ArrowRight size={20} aria-hidden />
            </span>
          </Link>
        </section>

        <div className="flex flex-wrap items-start gap-[24px]">
          <section
            id="spaces"
            aria-label="공간 목록"
            className="flex min-w-0 flex-col gap-[16px]"
            style={{ flex: "999 1 560px" }}
          >
            <div className="flex flex-wrap items-center justify-between gap-[12px]">
              <span className="flex flex-wrap items-center gap-[12px]">
                <h2 className="tracking-title m-0 text-[22px] font-extrabold">공간</h2>
                <RegionScopeChips scope={scope} />
              </span>
              <TypeFilters
                label="공간 종류"
                options={spaceFilters(false)}
                value={filter}
                onChange={setFilter}
                count={count}
                className="flex-wrap"
              />
            </div>

            {visible.length === 0 && (
              <p className="rounded-card bg-surface text-text-sub m-0 px-[24px] py-[48px] text-center text-[15px]">
                {loading ? "공간을 불러오는 중이에요" : "지금 지원할 수 있는 공간이 없어요"}
              </p>
            )}
            <div
              className="grid gap-[16px]"
              style={{ gridTemplateColumns: "repeat(auto-fill, minmax(262px, 1fr))" }}
            >
              {/* 공간 사진이 없어서 이미지 칸 없이 글자만: 판정 · 공간 종류를 첫 줄에. 카드를 자르지 않아야 키보드 초점 테두리가 보여요 */}
              {visible.map((it) => {
                return (
                  <article key={it.id} className="rounded-card bg-surface flex flex-col">
                    <Link
                      {...spaceLink(it)}
                      className="rounded-card text-text hover:text-text flex flex-1 flex-col gap-[8px] px-[20px] pt-[18px] pb-[20px] no-underline"
                    >
                      <span className="flex flex-wrap items-center gap-[8px]">
                        {it.verdict && <VerdictBadge verdict={it.verdict} />}
                        <SpaceTypeTag type={it.type} />
                      </span>
                      <span className="text-text-tertiary text-[13px]">{it.org}</span>
                      <span className="tracking-title text-[18px] font-extrabold">{it.title}</span>
                      <span className="text-[15px] font-semibold">{it.info}</span>
                      <span className="flex flex-wrap gap-[4px]">
                        {it.tags.map((t) => (
                          <InfoTag key={t}>{t}</InfoTag>
                        ))}
                      </span>
                      <span className="flex-1" />
                      <span className="border-line-soft mt-[4px] flex items-center justify-between border-t border-solid pt-[12px]">
                        <span className="text-text-sub text-[13px]">{it.money}</span>
                        <span className="text-[14px] font-extrabold">{it.due}</span>
                      </span>
                    </Link>
                  </article>
                );
              })}
            </div>
          </section>

          <aside
            aria-label="받을 수 있는 사업 지원"
            className="rounded-card bg-surface box-content flex min-w-0 flex-col gap-[4px] px-[24px] py-[22px]"
            style={{ flex: "1 1 300px" }}
          >
            <div className="mb-[6px] flex items-center justify-between">
              <h2 className="m-0 text-[18px] font-extrabold tracking-[-0.02em]">
                받을 수 있는 사업 지원
              </h2>
              <Link
                href={routes.bizSupport}
                className="inline-flex min-h-[44px] items-center gap-[2px] text-[14px] font-bold no-underline"
              >
                전체
                <ChevronRight size={16} aria-hidden />
              </Link>
            </div>
            {asideItems.map((s, i) => {
              const last = i === asideItems.length - 1;
              return (
                <Link
                  key={s.id}
                  href={s.href ?? routes.bizSupport}
                  className={cn(
                    "text-text hover:text-text flex flex-col gap-[6px] no-underline",
                    last
                      ? "pt-[12px] pb-[4px]"
                      : "border-line-soft border-b border-solid pt-[12px] pb-[14px]",
                  )}
                >
                  <span className="flex items-center justify-between gap-[8px]">
                    <SupportBadge status={s.status} size="sm" />
                    <span className="text-[13px] font-extrabold">{s.due}</span>
                  </span>
                  <span className="text-[16px] font-extrabold">{s.title}</span>
                  <span className="text-text-sub text-[14px]">{s.summary}</span>
                </Link>
              );
            })}
          </aside>
        </div>
      </WebMain>
    </WebPage>
  );
}
