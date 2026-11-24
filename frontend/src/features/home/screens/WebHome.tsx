"use client";

import { QueryFeedback } from "@/shared/states/QueryFeedback";

import Link from "next/link";
import {
  Building,
  ChevronRight,
  FileText,
  House,
  Landmark,
  Sparkles,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import { WebHeader } from "@/shared/layout/WebHeader";
import { WebMain, WebPage } from "@/shared/layout/Responsive";
import { VerdictBadge } from "@/shared/ui/Badge";
import { DeadlineAlertPrompt } from "@/features/alerts/components/DeadlineAlertPrompt";
import { useConditionSummary } from "@/features/conditions/useConditionSummary";
import { HomeConditionPrompt } from "@/features/home/HomeConditionPrompt";
import { useHomeSummary } from "@/features/home/queries";
import { cn } from "@/shared/lib/cn";
import { routes } from "@/shared/lib/routes";
import type { HomeNewsItem } from "@/features/home/mocks/home";

const newsIcon: Record<HomeNewsItem["kind"], LucideIcon> = {
  notice: Building,
  policy: Landmark,
  correction: FileText,
};

const newsHref = (item: HomeNewsItem) =>
  item.kind === "policy" ? routes.benefit(item.id) : routes.notice(item.id);

function SummaryCard({
  href,
  icon: Icon,
  label,
  value,
  note,
}: {
  href: string;
  icon: LucideIcon;
  label: string;
  value: string;
  note: string;
}) {
  return (
    <Link
      href={href}
      className="rounded-card bg-surface text-text hover:text-text flex flex-col gap-[18px] px-[26px] pt-[26px] pb-[24px] no-underline"
    >
      <span className="flex items-center justify-between">
        <span className="bg-brand-soft text-brand flex size-[48px] items-center justify-center rounded-[15px]">
          <Icon size={26} strokeWidth={1.8} aria-hidden />
        </span>
        <ChevronRight size={22} className="text-text-tertiary" aria-hidden />
      </span>
      <span className="flex flex-col gap-[4px]">
        <span className="text-text-sub text-[15px]">{label}</span>
        <span className="tracking-h1 text-[34px] font-extrabold">{value}</span>
      </span>
      <span className="text-text-sub text-[14px]">{note}</span>
    </Link>
  );
}

export function WebHome() {
  const conditions = useConditionSummary();
  const personalized = conditions.status === "ready" && conditions.hasConditions;
  const { data, loading, error, homes, benefits } = useHomeSummary(personalized);

  return (
    <WebPage>
      <WebHeader mode="home" current={routes.home} />
      <WebMain>
        {conditions.status === "loading" ? (
          <QueryFeedback label="저장한 조건" />
        ) : (
          <>
            <div className="flex flex-wrap items-end justify-between gap-[16px]">
              <div className="flex flex-col gap-[14px]">
                <h1 className="tracking-h1 m-0 text-[32px] font-extrabold">
                  {personalized ? "내 조건으로 찾은 결과예요" : "내 홈"}
                </h1>
                {personalized && (
                  <div className="flex flex-wrap items-center gap-[6px]">
                    {conditions.chips.map((c) => (
                      <span
                        key={c}
                        className="rounded-pill bg-surface text-text-sub px-[13px] py-[7px] text-[14px] font-semibold"
                      >
                        {c}
                      </span>
                    ))}
                    <Link
                      href={routes.profile}
                      className="text-brand-strong inline-flex min-h-[36px] items-center gap-[2px] px-[8px] text-[14px] font-bold no-underline"
                    >
                      조건 수정
                      <ChevronRight size={16} strokeWidth={2.2} aria-hidden />
                    </Link>
                  </div>
                )}
              </div>
            </div>

            {!personalized && <HomeConditionPrompt />}

            <section
              aria-label="요약"
              className="grid gap-[16px]"
              style={{ gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}
            >
              <SummaryCard href={routes.homes} icon={House} {...homes} />
              <SummaryCard href={routes.benefits} icon={Wallet} {...benefits} />
            </section>

            {(loading || error) && (
              <QueryFeedback error={error} label="공고·혜택 소식" queryKey={["home"]} />
            )}

            <div className="flex flex-wrap items-start gap-[24px]">
              <section
                aria-label="이번 주 새 소식"
                className="rounded-card bg-surface min-w-0 py-[8px]"
                style={{ flex: "999 1 560px" }}
              >
                <div className="flex items-center justify-between px-[26px] pt-[18px] pb-[10px]">
                  <h2 className="tracking-title m-0 text-[20px] font-extrabold">이번 주 새 소식</h2>
                  {personalized && (
                    <span className="text-text-tertiary text-[14px]">내 조건에 맞는 것만</span>
                  )}
                </div>
                {!loading && !error && data.news.length === 0 && (
                  <p className="text-text-sub m-0 px-[26px] py-[20px] text-[15px]">
                    이번 주에 새로 올라온 공고가 없어요
                  </p>
                )}
                {data.news.map((item) => {
                  const Icon = newsIcon[item.kind];
                  return (
                    <Link
                      key={item.id}
                      href={newsHref(item)}
                      className="text-text hover:text-text flex items-center gap-[16px] px-[26px] py-[16px] no-underline"
                    >
                      <span className="rounded-control bg-fill text-text flex size-[44px] flex-none items-center justify-center">
                        <Icon size={22} strokeWidth={1.8} aria-hidden />
                      </span>
                      <span className="flex min-w-0 flex-1 flex-col gap-[3px]">
                        <span className="text-text-tertiary text-[13px]">{item.meta}</span>
                        <span className="text-[17px] font-bold">{item.title}</span>
                      </span>
                      <span className="flex flex-none items-center gap-[10px]">
                        <span className="text-text-sub text-[14px] font-bold">{item.due}</span>
                        {personalized && <VerdictBadge verdict={item.verdict} />}
                      </span>
                    </Link>
                  );
                })}
                <Link
                  href={routes.homes}
                  className="border-line-soft text-text-sub hover:text-text-sub mx-[26px] mt-[4px] mb-[12px] flex min-h-[52px] items-center justify-center gap-[2px] border-t border-solid text-[15px] font-bold no-underline"
                >
                  전체 보기
                  <ChevronRight size={18} aria-hidden />
                </Link>
              </section>

              <aside className="flex min-w-0 flex-col gap-[16px]" style={{ flex: "1 1 320px" }}>
                {personalized && data.suggestedBenefit && (
                  <Link
                    href={routes.benefit(data.suggestedBenefit.id)}
                    className="rounded-card bg-brand-soft text-text hover:text-text flex flex-col gap-[10px] p-[24px] no-underline"
                  >
                    <span className="text-brand-strong inline-flex items-center gap-[6px] text-[14px] font-bold">
                      <Sparkles size={18} aria-hidden />
                      이런 혜택도 있어요
                    </span>
                    <span className="tracking-title text-[20px] font-extrabold">
                      {data.suggestedBenefit.title}
                    </span>
                    <span className="text-text-sub text-[15px] leading-[1.6]">
                      내 조건으로 받을 수 있는데 아직 안 본 혜택이에요
                    </span>
                    <span className="text-brand-strong inline-flex items-center gap-[2px] text-[15px] font-bold">
                      자세히 보기
                      <ChevronRight size={16} strokeWidth={2.2} aria-hidden />
                    </span>
                  </Link>
                )}

                <section
                  aria-label="마감 임박 공고"
                  className="rounded-card bg-surface flex flex-col gap-[6px] px-[24px] py-[22px]"
                >
                  <div className="mb-[6px] flex items-center justify-between">
                    <h2 className="tracking-title m-0 text-[18px] font-extrabold">
                      마감 임박 공고
                    </h2>
                    <Link
                      href={routes.homes}
                      className="text-brand-strong inline-flex min-h-[44px] items-center text-[14px] font-bold no-underline"
                    >
                      전체
                    </Link>
                  </div>
                  {!loading && !error && data.deadlines.length === 0 && (
                    <span className="text-text-sub text-[14px]">
                      2주 안에 마감하는 공고가 없어요
                    </span>
                  )}
                  {data.deadlines.map((d) => (
                    <Link
                      key={d.id}
                      href={routes.notice(d.id)}
                      className="text-text hover:text-text flex min-h-[52px] items-center justify-between gap-[10px] no-underline"
                    >
                      <span className="flex flex-col gap-[2px]">
                        <span className="text-[16px] font-bold">{d.title}</span>
                        <span className="text-text-tertiary text-[13px]">{d.meta}</span>
                      </span>
                      <span
                        className={cn(
                          "rounded-badge flex-none px-[10px] py-[5px] text-[13px] font-extrabold",
                          d.dday <= 3 ? "bg-text text-white" : "bg-fill text-text-sub",
                        )}
                      >
                        {d.dday === 0 ? "오늘" : `D-${d.dday}`}
                      </span>
                    </Link>
                  ))}
                </section>

                {personalized && <DeadlineAlertPrompt variant="web" />}
              </aside>
            </div>
          </>
        )}
      </WebMain>
    </WebPage>
  );
}
