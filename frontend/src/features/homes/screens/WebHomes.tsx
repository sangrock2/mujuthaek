"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { QueryFeedback } from "@/shared/states/QueryFeedback";
import Link from "next/link";
import { ChevronRight, List, Map as MapIcon } from "lucide-react";
import { WebHeader } from "@/shared/layout/WebHeader";
import { WebMain, WebPage } from "@/shared/layout/Responsive";
import { ScrollToTop } from "@/shared/ui/ScrollToTop";
import { InfiniteScroll } from "@/shared/ui/InfiniteScroll";
import { sortOptions, tenureParam, type SortOption } from "@/features/homes/filters";
import { HomesFilterPanel } from "@/features/homes/components/HomesFilterPanel";
import { useHomesFilters } from "@/features/homes/useHomesFilters";
import { HomesMap } from "@/features/homes/components/HomesMap";
import { EditConditionsLink } from "@/features/homes/components/EditConditionsLink";
import { RegionSelect } from "@/features/homes/components/RegionSelect";
import { ListingCard } from "@/features/homes/components/ListingCard";
import { useHomeList } from "@/features/homes/list";
import { useRegionFilter } from "@/features/homes/region";
import { track } from "@/shared/lib/analytics";
import { cn } from "@/shared/lib/cn";
import { routes } from "@/shared/lib/routes";

export function WebHomes() {
  const filters = useHomesFilters();
  const region = useRegionFilter();
  const list = useHomeList({ region, ...filters.listState });
  const visible = list.listings;
  const [view, setView] = useState<"list" | "map">("list");
  const results = useRef<HTMLElement>(null);
  const verdicts = useMemo(() => new Map(visible.map((l) => [l.id, l.verdict])), [visible]);
  const verdictOf = useCallback((id: string) => verdicts.get(id), [verdicts]);
  // 관심 등록은 카드의 하트가 서버에 저장해요 (features/favorites). 여기서는 GA 기록만
  const trackLike = (id: string) => {
    // 목록의 org는 「LH · 행복주택」처럼 유형이 붙어 있어요. 상세 화면과 같게 기관 이름만 보내요
    const org = visible.find((l) => l.id === id)?.org.split(" · ")[0];
    track("notice_bookmark", { notice_kind: "standard", agency: org || "-", via: "list" });
  };

  const resetFilters = () => {
    filters.reset();
    region.reset();
  };

  return (
    <WebPage className="stitch-surface h-dvh min-h-0 overflow-hidden [&>header]:shrink-0">
      <WebHeader mode="home" current={routes.homes} />
      <WebMain className="min-h-0 gap-6 pt-6 pb-5">
        <div className="flex shrink-0 flex-wrap items-end justify-between gap-3">
          <div className="flex flex-col gap-[6px]">
            <span className="text-text-sub text-sm font-semibold">
              {region.label} · {filters.mode}
            </span>
            <h1 className="tracking-h1 m-0 text-[32px] font-extrabold">주거 공고</h1>
          </div>
          <div className="flex flex-wrap items-center gap-[10px]">
            <div role="group" aria-label="보기 방식" className="flex rounded-full bg-white p-1">
              {(["list", "map"] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  aria-pressed={view === v}
                  onClick={() => setView(v)}
                  className={cn(
                    "inline-flex min-h-[36px] cursor-pointer items-center gap-1.5 rounded-full border-0 px-[14px] text-[14px]",
                    view === v
                      ? "bg-brand font-bold text-white"
                      : "text-text-sub bg-transparent font-semibold",
                  )}
                >
                  {v === "list" ? (
                    <List size={16} aria-hidden />
                  ) : (
                    <MapIcon size={16} aria-hidden />
                  )}
                  {v === "list" ? "목록" : "지도"}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="grid min-h-0 flex-1 grid-cols-[minmax(240px,1fr)_minmax(0,2.08fr)] gap-6">
          <aside
            aria-label="필터"
            tabIndex={0}
            className="flex min-h-0 min-w-0 flex-col gap-3 overflow-y-auto overscroll-contain p-0.5"
          >
            <section
              aria-label="내 조건 요약"
              className="flex flex-col gap-3 rounded-[16px] bg-white p-5"
            >
              <div className="flex items-center justify-between gap-2">
                <h2 className="m-0 text-base font-extrabold">내 조건 요약</h2>
                <EditConditionsLink />
              </div>
              {list.loading || list.error ? (
                <p className="text-text-sub m-0 text-sm" role="status">
                  {list.error ? "판정 결과를 불러오지 못했어요" : "판정 결과를 확인하고 있어요"}
                </p>
              ) : (
                <dl className="m-0 grid grid-cols-2 gap-2">
                  <div className="bg-brand-soft/45 rounded-[12px] p-3">
                    <dt className="text-text-sub text-[13px]">지원 가능</dt>
                    <dd className="text-brand-strong m-0 text-[20px] font-bold tabular-nums">
                      {list.eligibleCount}곳
                    </dd>
                  </div>
                  <div className="bg-fill rounded-[12px] p-3">
                    <dt className="text-text-sub text-[13px]">확인 필요</dt>
                    <dd className="m-0 text-[20px] font-bold tabular-nums">
                      {list.needsInputCount === null ? "–" : `${list.needsInputCount}곳`}
                    </dd>
                  </div>
                </dl>
              )}
              <div className="grid gap-1">
                <Link
                  href={routes.score}
                  className="text-text bg-fill hover:text-brand-strong inline-flex min-h-9 items-center justify-between rounded-[10px] px-3 text-[13px] font-semibold no-underline"
                >
                  청약 가점 계산 <ChevronRight size={15} aria-hidden />
                </Link>
                <Link
                  href={routes.loans}
                  className="text-text bg-fill hover:text-brand-strong inline-flex min-h-9 items-center justify-between rounded-[10px] px-3 text-[13px] font-semibold no-underline"
                >
                  대출 자격 확인 <ChevronRight size={15} aria-hidden />
                </Link>
              </div>
            </section>
            <div className="flex flex-col gap-3 rounded-[16px] bg-white p-5">
              <div className="flex items-center justify-between">
                <h2 className="m-0 text-base font-bold">필터</h2>
                <button
                  type="button"
                  onClick={resetFilters}
                  className="text-text-sub min-h-9 cursor-pointer border-0 bg-transparent px-2 text-[13px] font-semibold"
                >
                  초기화
                </button>
              </div>
              <fieldset className="m-0 flex flex-col border-0 p-0">
                <legend className="mb-[8px] p-0 text-[15px] font-extrabold">지역</legend>
                <div className="mb-2 flex flex-wrap gap-1">
                  {[
                    ["11", "서울"],
                    ["41", "경기"],
                    ["28", "인천"],
                    ["", "전체"],
                  ].map(([code, label]) => {
                    const selected = code
                      ? region.codes.length === 1 && region.codes[0] === code
                      : region.isAll;
                    return (
                      <button
                        key={label}
                        type="button"
                        aria-pressed={selected}
                        onClick={() => region.pick(code)}
                        className={cn(
                          "min-h-9 cursor-pointer rounded-full border-0 px-3 text-[13px] font-semibold",
                          selected ? "bg-brand text-white" : "text-text bg-fill",
                        )}
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
                <RegionSelect filter={region} />
              </fieldset>
              <HomesFilterPanel filters={filters} onReset={resetFilters} compact />
            </div>
          </aside>

          {view === "map" ? (
            <section aria-label="지도 보기" className="min-h-0 min-w-0">
              <HomesMap
                regionCodes={region.codes}
                tenure={tenureParam[filters.mode]}
                verdictOf={verdictOf}
                className="h-full min-h-0"
              />
            </section>
          ) : (
            <section
              ref={results}
              aria-label="공고 목록"
              tabIndex={0}
              className="min-h-0 min-w-0 overflow-y-auto overscroll-contain"
            >
              <div className="flex min-w-0 flex-col gap-3 p-0.5">
                <div className="bg-bg sticky top-0 z-10 pb-1">
                  <div className="flex min-h-12 flex-wrap items-center justify-between gap-2 rounded-[16px] bg-white px-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="sr-only">공고 목록</h2>
                      {!list.loading && !list.error && (
                        <span className="bg-brand-soft text-brand-strong rounded-full px-2.5 py-1 text-[13px] font-bold tabular-nums">
                          총 {list.resultCount.toLocaleString("ko-KR")}건
                        </span>
                      )}
                      <span className="text-text-sub text-[12px]">
                        예상 준비금은 대출에 따라 달라져요
                      </span>
                    </div>
                    <label className="text-text-sub inline-flex items-center gap-[8px] text-[14px]">
                      <span className="sr-only">정렬</span>
                      <select
                        value={filters.sort}
                        onChange={(e) => filters.setSort(e.target.value as SortOption)}
                        className="bg-surface text-text min-h-[44px] rounded-sm border-0 px-[14px] text-[15px] font-semibold"
                      >
                        {sortOptions.map((o) => (
                          <option key={o}>{o}</option>
                        ))}
                      </select>
                    </label>
                  </div>
                </div>
                <div className="grid gap-3">
                  {(list.loading || list.error) && (
                    <QueryFeedback error={list.error} label="공고" queryKey={["notices"]} />
                  )}
                  {!list.loading && !list.error && !list.hasMore && visible.length === 0 && (
                    <div className="rounded-card bg-surface text-text-sub col-span-full flex flex-col items-center gap-[12px] px-[24px] py-[48px] text-center text-[15px]">
                      {region.label}에는 지금 지원할 수 있는 공고가 없어요
                      <button
                        type="button"
                        onClick={region.reset}
                        className="bg-fill text-text min-h-[44px] cursor-pointer rounded-sm border-0 px-[16px] text-[14px] font-bold"
                      >
                        전체 지역 보기
                      </button>
                    </div>
                  )}
                  {visible.map((item) => (
                    <ListingCard
                      key={item.id}
                      item={item}
                      regionLabel={region.regionLabelOf(item)}
                      onLike={() => trackLike(item.id)}
                    />
                  ))}
                </div>
                <InfiniteScroll data={list} label="공고" scrollRoot={results} />
                <div className="flex flex-wrap items-center justify-center gap-x-[20px] gap-y-[12px]">
                  {!filters.checked.ineligible && (
                    <button
                      type="button"
                      onClick={filters.showIneligible}
                      className="text-text-sub inline-flex min-h-[44px] cursor-pointer items-center border-0 bg-transparent p-0 text-[14px] font-semibold"
                    >
                      지원 불가 공고까지 모두 보기
                      {list.ineligibleCount ? ` (${list.ineligibleCount}곳)` : ""}
                    </button>
                  )}
                </div>
              </div>
            </section>
          )}
        </div>
        {view === "list" && <ScrollToTop scrollRoot={results} />}
      </WebMain>
    </WebPage>
  );
}
