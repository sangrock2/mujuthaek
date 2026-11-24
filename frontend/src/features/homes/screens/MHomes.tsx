"use client";
import { PersonalizationSummary } from "@/features/conditions/components/PersonalizationSummary";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { QueryFeedback } from "@/shared/states/QueryFeedback";
import Link from "next/link";
import { SlidersHorizontal, X } from "lucide-react";
import { HomesFilterPanel } from "@/features/homes/components/HomesFilterPanel";
import { MTabBar } from "@/shared/layout/MTabBar";
import { MTopBar } from "@/shared/layout/MTopBar";
import { MPage } from "@/shared/layout/Responsive";
import { InfiniteScroll } from "@/shared/ui/InfiniteScroll";
import { tenureParam } from "@/features/homes/filters";
import { ListingCard } from "@/features/homes/components/ListingCard";
import { useHomeList } from "@/features/homes/list";
import { useHomesFilters, type HomesFilters } from "@/features/homes/useHomesFilters";
import { HomesMap } from "@/features/homes/components/HomesMap";
import { EditConditionsLink } from "@/features/homes/components/EditConditionsLink";
import { RegionSelect } from "@/features/homes/components/RegionSelect";
import { useRegionFilter } from "@/features/homes/region";
import { track } from "@/shared/lib/analytics";
import { cn } from "@/shared/lib/cn";
import { routes } from "@/shared/lib/routes";

/** 지도 모드에서 목록에 남기는 개수 */

/** 아래에서 올라오는 필터 시트 (입주 방식 · 정렬 · 유형 · 내 판정). 바깥을 누르거나 Esc로 닫아요 */
function FilterSheet({
  filters,
  onReset,
  onClose,
}: {
  filters: HomesFilters;
  onReset: () => void;
  onClose: () => void;
}) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const opener = document.activeElement;
    const previousOverflow = document.documentElement.style.overflow;
    document.documentElement.style.overflow = "hidden";
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key !== "Tab") return;
      const items = [
        ...(panel.current?.querySelectorAll<HTMLElement>(
          "button:not(:disabled), select:not(:disabled), input:not(:disabled), [href]",
        ) ?? []),
      ];
      const first = items[0];
      const last = items.at(-1);
      if (
        e.shiftKey &&
        (document.activeElement === first || document.activeElement === panel.current)
      ) {
        e.preventDefault();
        last?.focus();
      } else if (
        !e.shiftKey &&
        (document.activeElement === last || document.activeElement === panel.current)
      ) {
        e.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.documentElement.style.overflow = previousOverflow;
      if (opener instanceof HTMLElement) opener.focus({ preventScroll: true });
    };
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-end bg-[rgba(25,31,40,0.4)]" onClick={onClose}>
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label="필터"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        className="bg-surface flex max-h-[85dvh] w-full flex-col gap-[20px] overflow-hidden rounded-t-[24px] px-[20px] pt-[18px] pb-[max(20px,env(safe-area-inset-bottom))] outline-none"
      >
        <div className="flex items-center justify-between">
          <span className="text-[18px] font-extrabold">필터</span>
          <button
            type="button"
            onClick={onClose}
            aria-label="필터 닫기"
            className="text-text inline-flex size-[44px] cursor-pointer items-center justify-center border-0 bg-transparent"
          >
            <X size={22} aria-hidden />
          </button>
        </div>
        <div className="flex min-h-0 flex-col gap-[20px] overflow-y-auto overscroll-contain">
          <HomesFilterPanel filters={filters} onReset={onReset} withSort />
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-control bg-brand min-h-[52px] shrink-0 cursor-pointer border-0 text-[16px] font-extrabold text-white"
        >
          결과 보기
        </button>
      </div>
    </div>
  );
}

export function MHomes() {
  const [view, setView] = useState<"list" | "map">("list");
  const [sheet, setSheet] = useState(false);
  const isMap = view === "map";
  const filters = useHomesFilters();
  const region = useRegionFilter();
  const list = useHomeList({ region, ...filters.listState });
  const resetFilters = () => {
    filters.reset();
    region.reset();
  };
  // 관심 등록은 하트가 서버에 저장해요. 여기서는 GA 기록만 (웹 목록과 같은 값)
  const trackLike = (id: string) => {
    const org = list.listings.find((l) => l.id === id)?.org.split(" · ")[0];
    track("notice_bookmark", { notice_kind: "standard", agency: org || "-", via: "list" });
  };
  const visible = list.listings;
  const verdicts = useMemo(() => new Map(visible.map((l) => [l.id, l.verdict])), [visible]);
  const verdictOf = useCallback((id: string) => verdicts.get(id), [verdicts]);

  const viewButton = (v: "list" | "map", label: string) => (
    <button
      type="button"
      aria-pressed={view === v}
      onClick={() => setView(v)}
      className={cn(
        "min-h-[44px] cursor-pointer rounded-[9px] border-0 px-[12px] text-[14px] font-bold",
        view === v ? "bg-brand text-white" : "text-text-sub bg-transparent",
      )}
    >
      {label}
    </button>
  );

  return (
    <MPage className="stitch-surface">
      <MTopBar mode="home" />
      <main
        id="main-content"
        tabIndex={-1}
        className="flex flex-1 flex-col gap-[14px] px-[16px] pt-[20px] pb-[28px]"
      >
        <div className="flex flex-col gap-2 rounded-[16px] bg-white px-4 py-3">
          <div className="flex items-center justify-between gap-2">
            <h1 className="tracking-h1 m-0 text-[26px] font-extrabold">주거 공고</h1>
            <div
              role="group"
              aria-label="보기 방식"
              className="bg-fill flex shrink-0 rounded-full p-0.5"
            >
              {viewButton("list", "목록")}
              {viewButton("map", "지도")}
            </div>
          </div>
          <div className="text-text-sub flex flex-wrap items-center gap-x-3 text-[14px]">
            <span>
              <PersonalizationSummary
                kind="homes"
                loading={list.loading}
                error={list.error}
                eligible={list.eligibleCount}
                needsInput={list.needsInputCount}
              />
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-x-3">
            <EditConditionsLink />
            <Link
              href={routes.score}
              className="text-text bg-fill inline-flex min-h-9 items-center rounded-[10px] px-2 text-[12px] font-semibold no-underline"
            >
              청약 가점 계산
            </Link>
            <Link
              href={routes.loans}
              className="text-text bg-fill inline-flex min-h-9 items-center rounded-[10px] px-2 text-[12px] font-semibold no-underline"
            >
              대출 자격 확인
            </Link>
          </div>
        </div>

        <section aria-label="지역" className="px-[4px]">
          <RegionSelect filter={region} compact />
        </section>
        <div className="bg-bg sticky top-[56px] z-10 flex gap-[6px] overflow-x-auto px-[4px] py-2">
          <button
            type="button"
            aria-haspopup="dialog"
            onClick={() => setSheet(true)}
            className="rounded-pill bg-brand inline-flex min-h-[44px] flex-none cursor-pointer items-center gap-[6px] border-0 px-[14px] text-[14px] font-bold text-white"
          >
            <SlidersHorizontal size={16} aria-hidden />
            필터{filters.changedCount ? ` ${filters.changedCount}` : ""}
          </button>
          <button
            type="button"
            onClick={() => setSheet(true)}
            className="rounded-pill bg-surface text-text inline-flex min-h-[44px] flex-none cursor-pointer items-center border-0 px-[14px] text-[14px] font-semibold"
          >
            {filters.mode}
          </button>
          <button
            type="button"
            onClick={() => setSheet(true)}
            className="rounded-pill bg-surface text-text inline-flex min-h-[44px] flex-none cursor-pointer items-center border-0 px-[14px] text-[14px] font-semibold"
          >
            {filters.sort}
          </button>
        </div>

        {isMap ? (
          <HomesMap
            regionCodes={region.codes}
            tenure={tenureParam[filters.mode]}
            verdictOf={verdictOf}
            className="h-[min(60dvh,520px)]"
          />
        ) : (
          <>
            <div className="flex flex-wrap items-baseline justify-between gap-x-[14px] gap-y-[4px]">
              <h2 className="sr-only">공고 목록</h2>
              {!list.loading && !list.error && (
                <span className="bg-brand-soft text-brand-strong rounded-full px-2.5 py-1 text-[13px] font-bold tabular-nums">
                  총 {list.resultCount.toLocaleString("ko-KR")}건
                </span>
              )}
            </div>

            {(list.loading || list.error) && (
              <QueryFeedback error={list.error} label="공고" queryKey={["notices"]} />
            )}
            {!list.loading && !list.error && !list.hasMore && visible.length === 0 && (
              <div className="rounded-card bg-surface text-text-sub flex flex-col items-center gap-[12px] px-[20px] py-[36px] text-center text-[15px]">
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
            <InfiniteScroll data={list} label="공고" />
            {!filters.checked.ineligible && (
              <button
                type="button"
                onClick={filters.showIneligible}
                className="text-text-sub inline-flex min-h-[44px] cursor-pointer items-center self-center border-0 bg-transparent p-0 text-[14px] font-semibold"
              >
                지원 불가 공고까지 모두 보기
                {list.ineligibleCount ? ` (${list.ineligibleCount}곳)` : ""}
              </button>
            )}
          </>
        )}
      </main>
      <MTabBar mode="home" current={routes.homes} />
      {sheet && (
        <FilterSheet filters={filters} onReset={resetFilters} onClose={() => setSheet(false)} />
      )}
    </MPage>
  );
}
