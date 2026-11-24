"use client";

import { reportHref } from "@/features/me/tabs";
import { useRef, useState } from "react";
import Link from "next/link";
import { ChevronRight, Search } from "lucide-react";
import { WebHeader } from "@/shared/layout/WebHeader";
import { WebMain, WebPage } from "@/shared/layout/Responsive";
import {
  groupResults,
  resultHref,
  searchTypes,
  splitTitle,
  useSearch,
  type SearchTab,
} from "@/features/search/queries";
import { cn } from "@/shared/lib/cn";
import { ScrollToTop } from "@/shared/ui/ScrollToTop";
import { ResultBadge } from "./ResultBadge";

export function WebSearch() {
  const {
    query,
    setQuery,
    keyword,
    recent,
    remember,
    terms,
    results,
    totals,
    more,
    loading,
    error,
  } = useSearch();
  const [tab, setTab] = useState<SearchTab>("전체");
  const resultsRoot = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const tabs: SearchTab[] = ["전체", ...searchTypes];

  return (
    <WebPage className="stitch-surface h-dvh min-h-0 overflow-hidden [&>header]:shrink-0">
      <WebHeader mode="home" active="search" />
      <WebMain className="min-h-0 max-w-[920px] gap-4 pt-5 pb-0">
        <h1 className="tracking-h1 m-0 text-[30px] font-extrabold">통합 검색</h1>
        <form
          role="search"
          onSubmit={(e) => {
            e.preventDefault();
            remember();
          }}
          className="flex shrink-0 flex-col gap-[10px]"
        >
          <label className="relative flex">
            <span className="sr-only">공고, 혜택, 동네 검색</span>
            <Search
              size={24}
              strokeWidth={2.2}
              className="text-brand absolute top-1/2 left-[20px] -translate-y-1/2"
              aria-hidden
            />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="공고, 혜택 이름이나 기관으로 찾아요"
              ref={input}
              className="border-line-soft focus:border-brand bg-surface text-text min-h-[56px] min-w-0 flex-1 rounded-[18px] border border-solid pr-[20px] pl-[56px] text-[20px] font-bold"
            />
          </label>
        </form>

        <div role="group" aria-label="검색 결과 분류" className="flex shrink-0 flex-wrap gap-[6px]">
          {tabs.map((t) => {
            const on = t === tab;
            const count = t === "전체" ? searchTypes.reduce((n, k) => n + totals[k], 0) : totals[t];
            return (
              <button
                key={t}
                type="button"
                aria-pressed={on}
                onClick={() => setTab(t)}
                className={cn(
                  "rounded-pill min-h-[42px] cursor-pointer border-0 px-[16px] text-[15px] font-bold",
                  on ? "bg-brand text-white" : "bg-surface text-text-sub",
                )}
              >
                {t} {count}
              </button>
            );
          })}
        </div>

        <div
          ref={resultsRoot}
          role="region"
          aria-label="검색 결과"
          tabIndex={0}
          className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto overscroll-contain p-0.5 pb-6"
        >
          {(recent.length > 0 || !query.trim()) && (
            <div className="flex flex-wrap items-center gap-[6px]">
              <span className="text-text-sub mr-[4px] text-[14px]">
                {recent.length ? "최근 검색" : "추천 검색어"}
              </span>
              {(recent.length
                ? recent
                : ["국민임대", "청년안심주택", "신혼부부", "전세피해지원"]
              ).map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setQuery(r)}
                  className="rounded-pill bg-surface text-text-sub inline-flex min-h-[36px] cursor-pointer items-center border-0 px-[14px] text-[14px] font-semibold"
                >
                  {r}
                </button>
              ))}
            </div>
          )}
          {error && (
            <p
              role="alert"
              className="rounded-card bg-surface text-text-sub m-0 px-[24px] py-[40px] text-center text-[15px]"
            >
              검색하지 못했어요. 잠시 뒤 다시 해 주세요
            </p>
          )}
          {!error && loading && results.length === 0 && (
            <p
              role="status"
              className="rounded-card bg-surface text-text-sub m-0 px-[24px] py-[40px] text-center text-[15px]"
            >
              검색하는 중이에요
            </p>
          )}
          {!error && !loading && results.length === 0 && (
            <p className="rounded-card bg-surface text-text-sub m-0 px-[24px] py-[40px] text-center text-[15px]">
              {keyword
                ? `「${keyword}」에 맞는 공고·혜택이 없어요`
                : "지금 열린 공고·혜택이 없어요"}
            </p>
          )}
          {results.length > 0 &&
            groupResults(results, tab, totals)
              .filter((sec) => sec.count > 0)
              .map((sec) => (
                <section
                  key={sec.type}
                  aria-label={sec.type}
                  className="rounded-card bg-surface flex flex-col pt-[18px] pb-[8px]"
                >
                  <h2 className="text-text-sub m-0 px-[24px] pb-[6px] text-[16px] font-extrabold">
                    {sec.type === "공고"
                      ? "주거 공고 · 사업공간"
                      : sec.type === "혜택"
                        ? "혜택 · 지원금"
                        : sec.type}{" "}
                    <span className="rounded-pill bg-brand-soft text-brand-strong px-2 py-0.5 text-[12px] tabular-nums">
                      {sec.count}
                    </span>
                  </h2>
                  {sec.rows.map((r) => (
                    <Link
                      key={`${r.type}-${r.id}`}
                      href={resultHref(r)}
                      onClick={() => remember()}
                      className="text-text hover:text-text flex items-center gap-[16px] px-[24px] py-[14px] no-underline"
                    >
                      <span className="flex min-w-0 flex-1 flex-col gap-[3px]">
                        <span className="text-[17px] font-semibold">
                          {splitTitle(r.title, terms).map((p, i) => (
                            <span
                              key={i}
                              className={cn(
                                "rounded-[4px]",
                                p.hl
                                  ? "bg-brand-soft text-brand-strong font-extrabold"
                                  : "text-text",
                              )}
                            >
                              {p.t}
                            </span>
                          ))}
                        </span>
                        <span className="text-text-sub text-[14px]">{r.meta}</span>
                      </span>
                      <ResultBadge badge={r.badge} size="lg" />
                      <ChevronRight
                        size={18}
                        className="text-text-tertiary flex-none"
                        aria-hidden
                      />
                    </Link>
                  ))}
                  {more[sec.type] && (
                    <p className="text-text-sub m-0 px-[24px] py-[12px] text-[14px]">
                      {sec.count - sec.rows.length}건 더 있어요 · 검색어로 좁혀 보세요
                    </p>
                  )}
                </section>
              ))}

          <span className="text-text-sub text-center text-[14px]">
            찾는 게 없나요?{" "}
            <Link href={reportHref({ kind: "MISSING_NOTICE", from: "검색" })} className="font-bold">
              빠진 공고·정책 알려주기
            </Link>
          </span>
        </div>
        <ScrollToTop scrollRoot={resultsRoot} returnFocus={input} />
      </WebMain>
    </WebPage>
  );
}
