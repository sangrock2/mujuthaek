"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, ChevronLeft, ChevronRight } from "lucide-react";
import {
  WebContentMain,
  WebContentShell,
  WebContentTitle,
} from "@/components/content/WebContentShell";
import { FilterChip } from "@/components/ui/Chip";
import { useAnnouncements } from "@/features/content/queries";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import { announcementCategories, type AnnouncementFilter } from "@/mocks/content";

export function WebNotices() {
  const { data } = useAnnouncements();
  const [category, setCategory] = useState<AnnouncementFilter>("전체");
  const [selected, setSelected] = useState(data[0]?.id ?? "");

  // 중요 공지를 맨 위로
  const shown = data
    .filter((d) => category === "전체" || d.category === category)
    .sort((a, b) => Number(b.pinned) - Number(a.pinned));
  const index = Math.max(
    0,
    shown.findIndex((d) => d.id === selected),
  );
  const current = shown[index];
  const move = (step: number) =>
    setSelected(shown[(index + step + shown.length) % shown.length].id);

  return (
    <WebContentShell current={routes.announcements}>
      <WebContentMain>
        <div className="flex flex-wrap items-end justify-between gap-[16px]">
          <WebContentTitle title="공지사항" sub="새 기능, 점검, 정책 변경 소식을 알려드려요" />
          <div role="group" aria-label="공지 종류" className="flex flex-wrap gap-[6px]">
            {announcementCategories.map((c) => (
              <FilterChip
                key={c}
                selected={c === category}
                onClick={() => setCategory(c)}
                className="min-h-[42px] text-[15px] font-bold"
              >
                {c}
              </FilterChip>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-start gap-[20px]">
          <section
            aria-label="공지 목록"
            className="rounded-card bg-surface flex min-w-0 flex-col overflow-hidden"
            style={{ flex: "1 1 360px" }}
          >
            {shown.map((n) => {
              const on = n.id === current?.id;
              return (
                <button
                  key={n.id}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setSelected(n.id)}
                  className={cn(
                    "border-line-soft text-text flex cursor-pointer flex-col gap-[6px] border-0 border-b border-l-4 border-solid py-[18px] pr-[20px] pl-[16px] text-left",
                    on ? "border-l-brand bg-row-selected" : "bg-surface border-l-transparent",
                  )}
                >
                  <span className="flex w-full items-center gap-[8px]">
                    {n.pinned && (
                      <span className="rounded-tag bg-check-bg text-check-text px-[7px] py-[2px] text-[12px] font-extrabold">
                        중요
                      </span>
                    )}
                    <span className="text-brand-strong text-[13px] font-bold">{n.category}</span>
                    <span className="flex-1" />
                    <span className="text-text-sub text-[13px]">{n.date}</span>
                  </span>
                  <span className="text-[16px] leading-[1.45] font-bold">{n.title}</span>
                </button>
              );
            })}
          </section>

          {current && (
            <article
              aria-live="polite"
              className="rounded-card-lg bg-surface box-content flex min-w-0 flex-col gap-[20px] px-[36px] py-[32px]"
              style={{ flex: "999 1 560px" }}
            >
              <div className="border-line-soft flex flex-col gap-[10px] border-b border-solid pb-[20px]">
                <span className="flex flex-wrap gap-[6px]">
                  <span className="rounded-badge bg-brand-soft text-brand-strong px-[10px] py-[4px] text-[13px] font-bold">
                    {current.category}
                  </span>
                  {current.pinned && (
                    <span className="rounded-badge bg-check-bg text-check-text px-[10px] py-[4px] text-[13px] font-bold">
                      중요
                    </span>
                  )}
                </span>
                <h2 className="tracking-h1 m-0 text-[26px] leading-[1.35] font-extrabold">
                  {current.title}
                </h2>
                <span className="text-text-sub text-[14px]">{current.date} · 무주택자들 팀</span>
              </div>
              {current.body.map((p) => (
                <p key={p} className="text-text-body-long m-0 text-[17px] leading-[1.8]">
                  {p}
                </p>
              ))}
              {current.points.length > 0 && (
                <ul className="bg-bg m-0 flex list-disc flex-col gap-[8px] rounded-[18px] py-[18px] pr-[22px] pl-[40px] text-[16px] leading-[1.6]">
                  {current.points.map((pt) => (
                    <li key={pt}>{pt}</li>
                  ))}
                </ul>
              )}
              {current.cta && (
                <Link
                  href={current.cta.href}
                  className="rounded-control bg-brand inline-flex min-h-[52px] items-center gap-[6px] self-start px-[20px] text-[16px] font-extrabold text-white no-underline hover:text-white"
                >
                  {current.cta.label}
                  <ArrowRight size={18} strokeWidth={2.2} aria-hidden />
                </Link>
              )}
              <div className="border-line-soft flex justify-between gap-[10px] border-t border-solid pt-[18px]">
                <button
                  type="button"
                  onClick={() => move(-1)}
                  className="text-text-sub inline-flex min-h-[44px] cursor-pointer items-center gap-[4px] border-0 bg-transparent px-[6px] text-[15px] font-semibold"
                >
                  <ChevronLeft size={18} aria-hidden />
                  이전 공지
                </button>
                <button
                  type="button"
                  onClick={() => move(1)}
                  className="text-text-sub inline-flex min-h-[44px] cursor-pointer items-center gap-[4px] border-0 bg-transparent px-[6px] text-[15px] font-semibold"
                >
                  다음 공지
                  <ChevronRight size={18} aria-hidden />
                </button>
              </div>
            </article>
          )}
        </div>
      </WebContentMain>
    </WebContentShell>
  );
}
