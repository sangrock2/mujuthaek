"use client";

import { useDetailTitle } from "@/shared/lib/useDetailTitle";
import { BenefitEmptyState } from "../components/BenefitEmptyState";
import { InfiniteScroll } from "@/shared/ui/InfiniteScroll";

import { QueryFeedback } from "@/shared/states/QueryFeedback";
import { ReportButton } from "@/features/report/components/ReportButton";
import { useLayoutEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, ChevronLeft, ChevronRight } from "lucide-react";
import { WebHeader } from "@/shared/layout/WebHeader";
import { WebMain, WebPage } from "@/shared/layout/Responsive";
import { Badge, VerdictBadge } from "@/shared/ui/Badge";
import { CheckAction } from "@/shared/ui/CheckAction";
import { useBenefit, useBenefits, applyHref } from "@/features/benefits/queries";
import { track } from "@/shared/lib/analytics";
import { cn } from "@/shared/lib/cn";
import { routes } from "@/shared/lib/routes";
import {
  benefitCategories,
  type Benefit,
  type BenefitCategory,
} from "@/features/benefits/mocks/benefits";

type CatFilter = "전체" | BenefitCategory;

/** 목록에 없는 혜택을 열 때 상세가 오기 전 자리 값 */
const placeholder: Benefit = {
  id: "",
  cat: "주거",
  org: "",
  orgShort: "",
  title: "",
  amount: "",
  amountShort: "",
  dday: "",
  deadline: "",
  verdict: "check",
  budget: false,
  overlap: "",
  elig: [],
  how: [],
  docs: "",
  sourceUrl: "",
  policyUrl: "",
  applyUrl: "",
};

const eligLabel = { ok: "충족", check: "확인 필요", no: "해당 안 돼요" } as const;
const eligTone = { ok: "ok", check: "check", no: "neutral" } as const;

/** 대출 혜택(준비할 돈에 반영되는 혜택): 정확한 소득 · 순자산으로 상품마다 확인하는 화면으로 */
function LoanCheckLink() {
  return (
    <Link
      href={routes.loans}
      className="rounded-tile bg-brand-soft text-text hover:text-text flex items-center justify-between gap-[12px] px-[18px] py-[14px] no-underline"
    >
      <span className="flex flex-col gap-[2px]">
        <span className="text-brand-strong text-[15px] font-extrabold">대출 자격 확인하기</span>
        <span className="text-text-sub text-[14px]">
          정확한 소득 · 순자산으로 버팀목 · 디딤돌 상품마다 받을 수 있는지 봐요
        </span>
      </span>
      <ChevronRight size={18} className="text-brand-strong flex-none" aria-hidden />
    </Link>
  );
}

/** 고른 혜택: 목록 값으로 먼저 그리고, 상세·판정을 받으면 채워요 */
function SelectedBenefit({ base }: { base: Benefit }) {
  const { data, loading, error } = useBenefit(base.id, base);
  if (!data) {
    return (
      <div className="text-text-sub flex min-w-0 items-center justify-center p-[30px] text-[15px]">
        {(loading || error) && <QueryFeedback error={error} label="혜택" queryKey={["benefits"]} />}
      </div>
    );
  }
  return <BenefitDetail b={data} />;
}

function BenefitDetail({ b }: { b: Benefit }) {
  useDetailTitle(b.title);
  return (
    <div
      aria-live="polite"
      className="flex min-w-0 flex-col gap-[24px] px-6 pt-4 pb-7 [overflow-wrap:anywhere] xl:px-[30px]"
    >
      <div className="flex flex-col gap-[10px]">
        <div className="flex flex-wrap gap-[6px]">
          <VerdictBadge verdict={b.verdict} />
          <Badge tone="neutral">{b.cat}</Badge>
          {b.budget && (
            <Badge tone="neutral" className="font-semibold">
              내 집 &apos;준비할 돈&apos;에 반영
            </Badge>
          )}
        </div>
        <h2 className="tracking-h1 m-0 text-[28px] font-extrabold">{b.title}</h2>
        <span className="text-text-sub text-[15px]">{b.org}</span>
      </div>

      <dl
        className="m-0 grid gap-[10px]"
        style={{ gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }}
      >
        <div className="rounded-tile bg-bg px-[18px] py-[16px]">
          <dt className="text-text-sub text-[13px]">지원 내용</dt>
          <dd className="m-0 mt-[6px] text-[17px] leading-[1.4] font-extrabold">{b.amount}</dd>
        </div>
        <div className="rounded-tile bg-bg px-[18px] py-[16px]">
          <dt className="text-text-sub text-[13px]">신청 기한</dt>
          <dd className="m-0 mt-[6px] text-[17px] leading-[1.4] font-extrabold">{b.deadline}</dd>
        </div>
        <div className="rounded-tile bg-bg px-[18px] py-[16px]">
          <dt className="text-text-sub text-[13px]">함께 못 받는 혜택</dt>
          <dd className="m-0 mt-[6px] text-[15px] leading-[1.5] font-semibold">{b.overlap}</dd>
        </div>
      </dl>
      {b.budget && <LoanCheckLink />}

      <div className="flex flex-col">
        <div className="mb-[4px] flex items-center justify-between">
          <h3 className="tracking-title m-0 text-[19px] font-extrabold">내 자격 확인</h3>
          {b.sourceUrl && (
            <a
              href={b.sourceUrl}
              target="_blank"
              onClick={() => track("notice_source_open", { notice_kind: "benefit", via: "site" })}
              rel="noopener noreferrer"
              className="text-brand-strong hover:text-brand-strong inline-flex min-h-[44px] items-center text-[14px] font-bold no-underline"
            >
              근거 원문
            </a>
          )}
        </div>
        {b.reason && <p className="text-text-sub m-0 pb-[4px] text-[14px]">{b.reason}</p>}
        {b.elig.length === 0 && (
          <p className="text-text-sub m-0 py-[12px] text-[15px]">원문에 적힌 자격 조건이 없어요</p>
        )}
        {b.elig.map((e, i) => (
          <div
            key={`${i}-${e.label}`}
            className="border-line-soft flex items-center justify-between gap-[12px] border-b border-solid py-[12px]"
          >
            <span className="flex min-w-0 flex-col gap-[2px]">
              <span className="text-[15px]">{e.label}</span>
              {e.reason && <span className="text-text-sub text-[13px]">{e.reason}</span>}
            </span>
            {e.result === "check" ? (
              <CheckAction inputHref={e.inputHref} web />
            ) : (
              <Badge
                tone={eligTone[e.result]}
                className="inline-flex flex-none items-center gap-[5px] px-[10px] py-[4px] text-[14px]"
              >
                {eligLabel[e.result]}
              </Badge>
            )}
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-[12px]">
        <h3 className="tracking-title m-0 text-[19px] font-extrabold">신청 방법</h3>
        {b.how.length === 0 && (
          <p className="text-text-sub m-0 text-[15px]">정책 원문의 신청 방법을 확인해 주세요</p>
        )}
        <ol className="m-0 flex list-none flex-col gap-[10px] p-0">
          {b.how.map((text, i) => (
            <li key={text} className="flex items-center gap-[12px]">
              <span className="bg-brand-soft text-brand-strong flex size-[28px] flex-none items-center justify-center rounded-[9px] text-[14px] font-extrabold">
                {i + 1}
              </span>
              <span className="text-[15px]">{text}</span>
            </li>
          ))}
        </ol>
        <span className="text-text-sub text-[14px]">필요 서류 · {b.docs}</span>
      </div>

      <div className="border-line-soft flex flex-wrap items-center justify-between gap-[12px] border-t border-solid pt-[20px]">
        <ReportButton target={{ kind: "benefit", id: b.id }} screen="혜택 상세" />
        <div className="flex gap-[8px]">
          {b.policyUrl && (
            <a
              href={b.policyUrl}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => track("notice_source_open", { notice_kind: "benefit", via: "site" })}
              className="rounded-control bg-fill text-text hover:text-text inline-flex min-h-[52px] items-center px-[18px] text-[15px] font-bold no-underline"
            >
              정책 원문
            </a>
          )}
          {applyHref(b) && (
            <a
              href={applyHref(b)}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-control bg-brand inline-flex min-h-[52px] items-center gap-[6px] px-[20px] text-[16px] font-extrabold text-white no-underline hover:text-white"
            >
              신청하러 가기
              <ArrowRight size={18} strokeWidth={2.2} aria-hidden />
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

export function WebBenefits({ initialId }: { initialId?: string }) {
  const [cat, setCat] = useState<CatFilter>("전체");
  const data = useBenefits(cat === "전체" ? undefined : cat);
  const [selId, setSelId] = useState(initialId);
  const list = useRef<HTMLElement>(null);
  const detail = useRef<HTMLElement>(null);
  const selectionRequest = useRef(0);
  const [movingNext, setMovingNext] = useState(false);

  const selected =
    data.items.find((benefit) => benefit.id === selId) ??
    (selId && !data.loading ? { ...placeholder, id: selId } : data.items[0]);
  const selectedIndex = data.items.findIndex((benefit) => benefit.id === selected?.id);
  const total = cat === "전체" ? data.total : data.counts[cat];
  const selectedId = selected?.id;

  useLayoutEffect(() => {
    detail.current?.scrollTo(0, 0);
  }, [selectedId]);

  function selectBenefit(id: string, revealInList = false) {
    selectionRequest.current++;
    setMovingNext(false);
    setSelId(id);
    window.history.replaceState(null, "", routes.benefit(id));
    if (revealInList) {
      requestAnimationFrame(() => {
        list.current?.querySelector('[aria-pressed="true"]')?.scrollIntoView({ block: "nearest" });
      });
    }
  }

  async function moveNext() {
    const next = data.items[selectedIndex + 1];
    if (next) {
      selectBenefit(next.id, true);
    } else if (data.hasMore && !movingNext) {
      const request = ++selectionRequest.current;
      setMovingNext(true);
      try {
        const items = await data.loadMore();
        const index = items.findIndex((benefit) => benefit.id === selectedId);
        if (request === selectionRequest.current && index >= 0 && items[index + 1]) {
          selectBenefit(items[index + 1].id, true);
        }
      } finally {
        if (request === selectionRequest.current) setMovingNext(false);
      }
    }
  }

  const cats: CatFilter[] = ["전체", ...benefitCategories];
  const changeCategory = (category: CatFilter) => {
    if (category === cat) return;
    selectionRequest.current++;
    setMovingNext(false);
    list.current?.scrollTo(0, 0);
    setSelId(undefined);
    setCat(category);
    if (selId) window.history.replaceState(null, "", routes.benefits);
  };

  return (
    <WebPage className="stitch-surface h-dvh min-h-0 overflow-hidden [&>header]:shrink-0">
      <WebHeader mode="home" current={routes.benefits} />
      <WebMain className="min-h-0 gap-[16px] pt-[24px] pb-[16px]">
        <div className="flex shrink-0 flex-wrap items-end justify-between gap-[16px]">
          <div className="flex flex-col gap-[6px]">
            <h1 className="tracking-h1 m-0 text-[32px] font-extrabold">내 혜택</h1>
            {data.yearlyAmount !== "–" && (
              <span className="text-text-sub text-sm">연간 예상 혜택 {data.yearlyAmount}</span>
            )}
          </div>
          <div role="group" aria-label="분야" className="flex flex-wrap gap-[6px]">
            {cats.map((c) => {
              const count = c === "전체" ? data.total : data.counts[c];
              const on = c === cat;
              return (
                <button
                  key={c}
                  type="button"
                  aria-pressed={on}
                  onClick={() => changeCategory(c)}
                  className={cn(
                    "rounded-pill min-h-[42px] cursor-pointer border-0 px-[16px] text-[15px] font-bold",
                    on ? "bg-brand text-white" : "bg-surface text-text-sub",
                  )}
                >
                  {c}
                  {!data.loading && !data.error && ` ${count}`}
                </button>
              );
            })}
          </div>
        </div>

        <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,360px)_minmax(0,1fr)] gap-[20px]">
          <section
            ref={list}
            aria-label="혜택 목록"
            tabIndex={0}
            className="rounded-card bg-surface min-h-0 min-w-0 overflow-y-auto overscroll-contain focus-visible:outline-offset-[-3px]"
          >
            <div className="bg-surface border-line-soft sticky top-0 z-10 flex items-center justify-between gap-3 border-b px-4 py-3">
              <h2 className="m-0 text-base font-extrabold">혜택 목록</h2>
              {!data.loading && !data.error && (
                <span className="text-text-sub text-sm tabular-nums">
                  전체 {total.toLocaleString("ko-KR")}건
                </span>
              )}
            </div>
            <div className="flex min-w-0 flex-col gap-1 p-2">
              {(data.loading || data.error) && (
                <QueryFeedback error={data.error} label="혜택" queryKey={["benefits"]} />
              )}
              {!data.loading && !data.error && !data.hasMore && data.items.length === 0 && (
                <BenefitEmptyState
                  filtered={cat !== "전체"}
                  onReset={() => changeCategory("전체")}
                />
              )}
              {data.items.map((b, index) => {
                const on = b.id === selected?.id;
                return (
                  <button
                    key={b.id}
                    type="button"
                    aria-pressed={on}
                    onClick={() => selectBenefit(b.id)}
                    className={cn(
                      "rounded-control text-text flex cursor-pointer scroll-mt-14 items-start gap-3 border-0 px-3 py-3 text-left",
                      on ? "bg-brand-soft" : "bg-surface hover:bg-fill",
                    )}
                  >
                    <span className="text-text-sub pt-0.5 text-[12px] font-bold tabular-nums">
                      {index + 1}
                    </span>
                    <span className="flex min-w-0 flex-1 flex-col gap-1">
                      <span className="flex w-full items-center justify-between gap-[8px]">
                        <span className="text-text-tertiary text-[13px]">
                          {b.cat} · {b.org}
                        </span>
                        <span className="text-text-sub text-[14px] font-extrabold">{b.dday}</span>
                      </span>
                      <span className="tracking-title text-[18px] font-extrabold">{b.title}</span>
                      <span className="flex w-full items-center justify-between gap-[8px]">
                        <span className="text-[15px] font-semibold">{b.amount}</span>
                        <VerdictBadge
                          verdict={b.verdict}
                          size="md"
                          className="flex-none text-[12px]"
                        />
                      </span>
                    </span>
                  </button>
                );
              })}
              <InfiniteScroll data={data} label="혜택" scrollRoot={list} />
            </div>
          </section>

          {selected && (
            <section
              ref={detail}
              aria-label="혜택 상세"
              tabIndex={0}
              className="rounded-card-lg bg-surface min-h-0 min-w-0 overflow-y-auto overscroll-contain"
            >
              {selectedIndex >= 0 && (
                <div className="bg-surface border-line-soft sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 border-b px-6 py-2">
                  <span
                    aria-live="polite"
                    className="text-text-sub text-sm font-semibold tabular-nums"
                  >
                    {selectedIndex + 1} / {total.toLocaleString("ko-KR")}번째 확인 중
                  </span>
                  <div className="flex gap-1">
                    <button
                      type="button"
                      aria-label="이전 혜택"
                      disabled={selectedIndex === 0}
                      onClick={() => selectBenefit(data.items[selectedIndex - 1].id, true)}
                      className="rounded-control bg-fill text-text flex size-11 cursor-pointer items-center justify-center border-0 disabled:opacity-40"
                    >
                      <ChevronLeft size={18} aria-hidden />
                    </button>
                    <button
                      type="button"
                      aria-label="다음 혜택"
                      disabled={
                        movingNext || (selectedIndex === data.items.length - 1 && !data.hasMore)
                      }
                      onClick={() => void moveNext()}
                      className="rounded-control bg-fill text-text flex size-11 cursor-pointer items-center justify-center border-0 disabled:opacity-40"
                    >
                      <ChevronRight size={18} aria-hidden />
                    </button>
                  </div>
                </div>
              )}
              <SelectedBenefit key={selected.id} base={selected} />
            </section>
          )}
        </div>
      </WebMain>
    </WebPage>
  );
}
