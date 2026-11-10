"use client";

import { CardFavoriteHeart } from "@/components/favorites/FavoriteButtons";
import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { WebHeader } from "@/components/layout/WebHeader";
import { WebMain, WebPage } from "@/components/layout/Responsive";
import { RankChip, VerdictBadge } from "@/components/ui/Badge";
import { InfoTag } from "@/components/ui/Chip";
import { sortOptions, tenureParam, type SortOption } from "@/features/homes/filters";
import { HomesFilterPanel } from "@/components/homes/HomesFilterPanel";
import { useHomesFilters } from "@/features/homes/useHomesFilters";
import { HomesMap } from "@/components/homes/HomesMap";
import { EditConditionsLink } from "@/components/homes/EditConditionsLink";
import { RegionSelect } from "@/components/homes/RegionSelect";
import { useHomeList } from "@/features/homes/list";
import { useRegionFilter } from "@/features/homes/region";
import { track } from "@/lib/analytics";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import type { HomeListing } from "@/mocks/homes";

function ListingCard({
  item,
  regionLabel,
  onLike,
}: {
  item: HomeListing;
  regionLabel: string;
  /** 관심 등록할 때 (GA 기록) */
  onLike: () => void;
}) {
  // 공고 사진이 없어서 이미지 칸 없이 글자만: 판정 · 순위를 첫 줄에, 관심 하트는 오른쪽 위에.
  // 링크가 카드를 채워서 카드를 자르지 않아요 (overflow-hidden이면 키보드 초점 테두리가 잘려요)
  return (
    <article className="rounded-card bg-surface relative flex flex-col">
      <CardFavoriteHeart
        type="NOTICE"
        id={item.id}
        onAdd={onLike}
        className="absolute top-[10px] right-[10px]"
      />
      <Link
        href={routes.notice(item.id)}
        className="rounded-card text-text hover:text-text flex flex-1 flex-col gap-[8px] px-[20px] pt-[18px] pb-[20px] no-underline"
      >
        <span className="flex min-h-[28px] flex-wrap items-center gap-[4px] pr-[40px]">
          <VerdictBadge verdict={item.verdict} />
          {item.rank && <RankChip rank={item.rank} />}
        </span>
        <span className="text-text-tertiary text-[13px]">
          {item.org} · {regionLabel}
        </span>
        <span className="tracking-title text-[18px] font-extrabold">{item.title}</span>
        {item.price && <span className="text-[15px] font-semibold">{item.price}</span>}
        <span className="flex flex-wrap gap-[4px]">
          {item.life && <InfoTag>{item.life}</InfoTag>}
          {item.tags.map((t) => (
            <InfoTag key={t}>{t}</InfoTag>
          ))}
        </span>
        <span className="border-line-soft mt-[4px] flex items-center justify-between border-t border-solid pt-[12px]">
          <span className="text-text-sub text-[13px]">
            {item.prepAmount ? (
              <>
                준비할 돈 <strong className="text-text">{item.prepAmount}</strong>
              </>
            ) : (
              item.prepNote
            )}
          </span>
          <span className="text-[14px] font-extrabold">{item.dueLong ?? item.due}</span>
        </span>
      </Link>
    </article>
  );
}

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
      <WebMain>
        <div className="flex flex-wrap items-end justify-between gap-[16px]">
          <div className="flex flex-col gap-[6px]">
            <h1 className="tracking-h1 m-0 text-[32px] font-extrabold">내 집</h1>
            <span className="text-text-sub flex flex-wrap items-center gap-x-[12px] text-[16px]">
              <span>
                내 조건으로 지원할 수 있는 곳{" "}
                <strong className="text-brand-strong">{list.eligibleCount}곳</strong>
                {list.needsInputCount ? ` · 확인 필요 ${list.needsInputCount}곳` : ""}
              </span>
              <EditConditionsLink />
              <Link
                href={routes.score}
                className="text-brand-strong hover:text-brand-strong inline-flex min-h-[36px] items-center text-[14px] font-bold no-underline"
              >
                청약 가점 계산
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
                      ? "bg-text font-bold text-white"
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

        <div className="flex flex-wrap items-start gap-[24px]">
          <aside
            aria-label="필터"
            className="rounded-card bg-surface box-content flex min-w-0 flex-col gap-[22px] p-[22px]"
            style={{ flex: "1 1 250px" }}
          >
            <fieldset className="m-0 flex flex-col border-0 p-0">
              <legend className="mb-[8px] p-0 text-[15px] font-extrabold">지역</legend>
              <RegionSelect filter={region} />
            </fieldset>
            <HomesFilterPanel filters={filters} onReset={resetFilters} />
          </aside>

          <section
            aria-label="공고 목록"
            className="flex min-w-0 flex-col gap-[20px]"
            style={{ flex: "999 1 560px" }}
          >
            {view === "map" && (
              <HomesMap
                regionCodes={region.codes}
                tenure={tenureParam[filters.mode]}
                verdictOf={verdictOf}
                className="h-[520px]"
              />
            )}
            <div
              className="grid gap-[16px]"
              style={{ gridTemplateColumns: "repeat(auto-fill, minmax(262px, 1fr))" }}
            >
              {list.loading && (
                <div className="rounded-card bg-surface text-text-sub col-span-full px-[24px] py-[48px] text-center text-[15px]">
                  내 조건으로 공고를 판정하는 중이에요
                </div>
              )}
              {list.error && (
                <div
                  role="alert"
                  className="rounded-card bg-surface text-text-sub col-span-full px-[24px] py-[48px] text-center text-[15px]"
                >
                  공고를 불러오지 못했어요. 잠시 뒤 다시 시도해 주세요
                </div>
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
