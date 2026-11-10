"use client";

import { useState } from "react";
import { useSiteLife } from "@/features/notice/area";
import { cn } from "@/lib/cn";
import type { NoticeLifeSite, StandardNotice } from "@/mocks/notice";

type Props = {
  life: NonNullable<StandardNotice["life"]>;
  variant: "web" | "mobile";
  /** 보여줄 단지 (sites[].id). 없으면 직접 고른 단지, 그것도 없으면 점수가 가장 높은 단지 */
  siteId?: string;
  onSiteChange?: (siteId: string) => void;
};

/** "82점" · 단지마다 다르면 "52~82점" */
export function lifeScoreText(life: NonNullable<StandardNotice["life"]>) {
  return life.min === life.score ? `${life.score}점` : `${life.min}~${life.score}점`;
}

/** 고른 단지의 항목 점수 · 가까운 시설 */
function SiteDetail({ site, web }: { site: NoticeLifeSite; web: boolean }) {
  const { data, loading, error } = useSiteLife(site.areaId);
  if (!site.areaId || error) {
    return (
      <p className="text-text-sub m-0 text-[14px]">
        {error ? "항목별 점수를 불러오지 못했어요" : "항목별 점수를 아직 계산하지 못했어요"}
      </p>
    );
  }
  if (loading || !data) {
    return <p className="text-text-sub m-0 text-[14px]">항목별 점수를 불러오는 중이에요</p>;
  }
  return (
    <div className="flex flex-col gap-[14px]">
      {data.categories.length > 0 && (
        <div
          className={cn("grid", web ? "gap-x-[24px] gap-y-[12px]" : "gap-[10px]")}
          style={{ gridTemplateColumns: web ? "repeat(auto-fit, minmax(170px, 1fr))" : "1fr" }}
        >
          {data.categories.map((c) => (
            <div key={c.key} className="flex flex-col gap-[6px]">
              <span className="flex justify-between text-[15px]">
                <span>{c.label}</span>
                <strong>{c.score}점</strong>
              </span>
              <span className="bg-fill h-[8px] overflow-hidden rounded-[4px]">
                <span
                  className="bg-brand block h-full rounded-[4px]"
                  style={{ width: `${c.score}%` }}
                />
              </span>
            </div>
          ))}
        </div>
      )}
      {data.facts.length > 0 && (
        <dl
          className="m-0 grid gap-[8px]"
          style={{
            gridTemplateColumns: web ? "repeat(auto-fit, minmax(150px, 1fr))" : "1fr 1fr",
          }}
        >
          {data.facts.map((f) => (
            <div key={f.label} className="bg-bg rounded-control px-[14px] py-[10px]">
              <dt className="text-text-sub text-[12px]">{f.label}</dt>
              <dd className="mx-0 mt-[2px] mb-0 text-[15px] font-extrabold">{f.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {data.approximate && (
        <span className="text-text-sub text-[13px]">
          정확한 주소를 못 찾아서 동네 중심 위치로 계산했어요
        </span>
      )}
    </div>
  );
}

/** 공고 생활권: 단지마다 점수가 있어요. 단지가 여럿이면 골라서 항목을 봐요 */
export function LifeCard({ life, variant, siteId, onSiteChange }: Props) {
  const web = variant === "web";
  const [picked, setPicked] = useState<string | null>(null);
  const many = life.sites.length > 1;
  const site = life.sites.find((s) => s.id === (siteId ?? picked)) ?? life.sites[0];
  const pick = (id: string) => {
    setPicked(id);
    onSiteChange?.(id);
  };
  const Heading = web ? "h2" : "h3";

  return (
    <section
      id="life"
      aria-labelledby="life-h"
      className={cn(
        "bg-surface flex scroll-mt-[80px] flex-col",
        web
          ? "rounded-card-lg gap-[18px] px-[30px] py-[28px]"
          : "rounded-card mx-[16px] gap-[12px] px-[20px] py-[16px]",
      )}
    >
      <div className="flex flex-col gap-[4px]">
        <Heading
          id="life-h"
          className={cn("m-0 font-extrabold", web ? "tracking-title text-[21px]" : "text-[17px]")}
        >
          생활권 <span className="text-brand">{lifeScoreText(life)}</span>
        </Heading>
        <span className="text-text-sub text-[14px]">
          {many
            ? `단지 ${life.sites.length}곳 · 단지마다 위치가 달라서 점수도 따로 매겨요`
            : "교통 · 학교 · 공원 · 편의시설 · 병원을 같은 비중으로 매겼어요"}
        </span>
      </div>

      {many ? (
        <div role="radiogroup" aria-label="단지" className="flex flex-col gap-[8px]">
          {life.sites.map((s) => {
            const on = s.id === site.id;
            return (
              <div
                key={s.id}
                className={cn(
                  "rounded-tile flex flex-col border-2 border-solid",
                  on ? "border-brand" : "border-line-soft",
                )}
              >
                <button
                  type="button"
                  role="radio"
                  aria-checked={on}
                  onClick={() => pick(s.id)}
                  className="text-text flex min-h-[52px] cursor-pointer items-center justify-between gap-[10px] border-0 bg-transparent px-[14px] py-[10px] text-left"
                >
                  <span className="flex min-w-0 flex-col gap-[2px]">
                    <span className="text-[15px] font-bold">{s.name}</span>
                    {s.tags.length > 0 && (
                      <span className="text-text-sub text-[13px]">{s.tags.join(" · ")}</span>
                    )}
                  </span>
                  <strong className={cn("flex-none text-[17px]", on ? "text-brand" : "text-text")}>
                    {s.score}점
                  </strong>
                </button>
                {on && (
                  <div className="px-[14px] pt-[4px] pb-[14px]">
                    <SiteDetail site={s} web={web} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <>
          {site.tags.length > 0 && (
            <div className="flex flex-wrap gap-[6px]">
              {site.tags.map((t) => (
                <span
                  key={t}
                  className="bg-brand-soft text-brand-strong rounded-badge px-[8px] py-[3px] text-[13px] font-bold"
                >
                  {t}
                </span>
              ))}
            </div>
          )}
          <SiteDetail site={site} web={web} />
        </>
      )}
    </section>
  );
}
