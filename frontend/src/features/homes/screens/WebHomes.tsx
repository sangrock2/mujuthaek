"use client";

import { PersonalizationSummary } from "@/features/conditions/components/PersonalizationSummary";
import { useCallback, useMemo, useState } from "react";
import { QueryFeedback } from "@/shared/states/QueryFeedback";
import Link from "next/link";
import { WebHeader } from "@/shared/layout/WebHeader";
import { WebMain, WebPage } from "@/shared/layout/Responsive";
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
    <WebPage>
      <WebHeader mode="home" current={routes.homes} />
      <WebMain className="gap-[16px] pt-[28px]">
        <div className="rounded-card border-line-soft bg-surface flex flex-wrap items-end justify-between gap-[12px] border p-[22px]">
          <div className="flex flex-col gap-[6px]">
            <h1 className="tracking-h1 m-0 text-[32px] font-extrabold">주거 공고</h1>
            <span className="text-text-sub flex flex-wrap items-center gap-x-[12px] text-[16px]">
              <span>
                <PersonalizationSummary
                  kind="homes"
                  loading={list.loading}
                  error={list.error}
                  eligible={list.eligibleCount}
                  needsInput={list.needsInputCount}
                />
              </span>
              <EditConditionsLink />
              <Link
                href={routes.score}
                className="text-brand-strong hover:text-brand-strong inline-flex min-h-[36px] items-center text-[14px] font-bold no-underline"
              >
                청약 가점 계산
              </Link>
              <Link
                href={routes.loans}
                className="text-brand-strong hover:text-brand-strong inline-flex min-h-[36px] items-center text-[14px] font-bold no-underline"
              >
                대출 자격 확인
              </Link>
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-[10px]">
            <div role="group" aria-label="보기 방식" className="bg-surface flex rounded-sm p-[4px]">
              {(["list", "map"] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  aria-pressed={view === v}
                  onClick={() => setView(v)}
                  className={cn(
                    "min-h-[36px] cursor-pointer rounded-[9px] border-0 px-[14px] text-[14px]",
                    view === v
                      ? "bg-brand font-bold text-white"
                      : "text-text-sub bg-transparent font-semibold",
                  )}
                >
                  {v === "list" ? "목록" : "지도"}
                </button>
              ))}
            </div>
            <label className="text-text-sub inline-flex items-center gap-[8px] text-[14px]">
              정렬
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

        <div className="grid grid-cols-[248px_minmax(0,1fr)] items-start gap-[16px]">
          <aside
            aria-label="필터"
            className="rounded-card border-line-soft bg-surface flex min-w-0 flex-col gap-[17px] border p-[16px]"
          >
            <fieldset className="m-0 flex flex-col border-0 p-0">
              <legend className="mb-[8px] p-0 text-[15px] font-extrabold">지역</legend>
              <RegionSelect filter={region} />
            </fieldset>
            <HomesFilterPanel filters={filters} onReset={resetFilters} />
          </aside>

          <section aria-label="공고 목록" className="flex min-w-0 flex-col gap-[20px]">
            <div className="flex flex-wrap items-baseline justify-between gap-x-[14px] gap-y-[4px]">
              <h2 className="tracking-title m-0 text-[17px] font-extrabold">공고 목록</h2>
              <p className="text-text-sub text-[12px]">
                예상 준비금은 대출 승인액과 부대비용에 따라 달라져요.
              </p>
            </div>
            {view === "map" && (
              <HomesMap
                regionCodes={region.codes}
                tenure={tenureParam[filters.mode]}
                verdictOf={verdictOf}
                className="h-[520px]"
              />
            )}
            <div className="grid gap-[12px] xl:grid-cols-2">
              {(list.loading || list.error) && (
                <QueryFeedback error={list.error} label="공고" queryKey={["notices"]} />
              )}
              {!list.loading && !list.error && visible.length === 0 && (
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
            <div className="flex flex-wrap items-center justify-center gap-x-[20px] gap-y-[12px]">
              {list.hasMore && (
                <button
                  type="button"
                  onClick={list.loadMore}
                  disabled={list.loadingMore}
                  className="rounded-control bg-surface text-text min-h-[52px] cursor-pointer border-0 px-[28px] text-[15px] font-bold disabled:cursor-default disabled:opacity-60"
                >
                  {list.loadingMore
                    ? "불러오는 중"
                    : list.remaining
                      ? `${list.remaining}곳 더 보기`
                      : "더 보기"}
                </button>
              )}
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
          </section>
        </div>
      </WebMain>
    </WebPage>
  );
}
