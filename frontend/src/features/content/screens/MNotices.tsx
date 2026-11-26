"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { cn } from "@/shared/lib/cn";
import { CustomerCenterHeader } from "@/features/content/components/WebContentShell";
import { FilterChip } from "@/shared/ui/Chip";
import { useAnnouncements } from "@/features/content/queries";
import { routes } from "@/shared/lib/routes";
import { announcementCategories, type AnnouncementFilter } from "@/features/content/mocks/content";

export function MNotices() {
  const { data } = useAnnouncements();
  const [category, setCategory] = useState<AnnouncementFilter>("전체");
  const [openId, setOpenId] = useState<string | null>(null);

  // 중요 공지를 맨 위로 (웹과 같아요)
  const shown = data
    .filter((d) => category === "전체" || d.category === category)
    .sort((a, b) => Number(b.pinned) - Number(a.pinned));
  const index = shown.findIndex((d) => d.id === openId);
  const current = index >= 0 ? shown[index] : data.find((d) => d.id === openId);

  const open = (id: string | null) => {
    setOpenId(id);
    window.scrollTo({ top: 0 });
  };

  return (
    <div className="stitch-surface bg-bg text-text flex min-h-screen w-full flex-col">
      <CustomerCenterHeader current={routes.announcements} sticky />
      <main id="main-content" tabIndex={-1} className="flex flex-1 flex-col gap-4 px-4 py-6">
        <div>
          <h1 className="tracking-h1 m-0 text-[26px] font-extrabold">공지사항</h1>
          {!current && (
            <p className="text-text-sub mt-1 mb-0 text-sm">
              새 기능, 점검, 정책 변경 소식을 알려드려요
            </p>
          )}
        </div>
        {current ? (
          <article
            aria-label="공지 상세"
            className="rounded-card bg-surface flex flex-col gap-4 p-5 [overflow-wrap:anywhere]"
          >
            <button
              type="button"
              onClick={() => open(null)}
              className="text-text-sub min-h-[44px] cursor-pointer self-start border-0 bg-transparent p-0 text-[14px] font-semibold"
            >
              ← 목록
            </button>
            <span className="flex gap-[6px]">
              <span className="rounded-badge bg-brand-soft text-brand-strong px-[9px] py-[4px] text-[13px] font-bold">
                {current.category}
              </span>
              {current.pinned && (
                <span className="rounded-badge bg-check-bg text-check-text px-[9px] py-[4px] text-[13px] font-bold">
                  중요
                </span>
              )}
            </span>
            <h2 className="tracking-h1 m-0 text-[22px] leading-[1.4] font-extrabold">
              {current.title}
            </h2>
            <span className="border-line-soft text-text-sub border-b border-solid pb-[14px] text-[13px]">
              {current.date} · 무주택자들 팀
            </span>
            {current.body.map((p) => (
              <p key={p} className="text-text-body-long m-0 text-[16px] leading-[1.8]">
                {p}
              </p>
            ))}
            {current.points.length > 0 && (
              <ul className="bg-bg m-0 flex list-disc flex-col gap-[6px] rounded-[16px] py-[14px] pr-[16px] pl-[32px] text-[15px] leading-[1.6]">
                {current.points.map((pt) => (
                  <li key={pt}>{pt}</li>
                ))}
              </ul>
            )}
            {current.cta && (
              <Link
                href={current.cta.href}
                className="rounded-control bg-brand flex min-h-[52px] items-center justify-center text-[16px] font-extrabold text-white no-underline hover:text-white"
              >
                {current.cta.label}
              </Link>
            )}
            {index >= 0 && shown.length > 1 && (
              <div className="border-line-soft flex justify-between gap-[10px] border-t border-solid pt-[14px]">
                <button
                  type="button"
                  disabled={index === 0}
                  onClick={() => open(shown[index - 1].id)}
                  className="text-text-sub min-h-[44px] cursor-pointer border-0 bg-transparent px-[4px] text-[14px] font-semibold disabled:opacity-40"
                >
                  ‹ 이전 공지
                </button>
                <button
                  type="button"
                  disabled={index === shown.length - 1}
                  onClick={() => open(shown[index + 1].id)}
                  className="text-text-sub min-h-[44px] cursor-pointer border-0 bg-transparent px-[4px] text-[14px] font-semibold disabled:opacity-40"
                >
                  다음 공지 ›
                </button>
              </div>
            )}
          </article>
        ) : (
          <section aria-label="공지 목록" className="flex flex-col gap-2">
            <div className="rounded-card bg-surface flex flex-wrap items-center justify-between gap-x-2 p-2">
              <div role="group" aria-label="공지 종류" className="flex flex-wrap gap-1">
                {announcementCategories.map((c) => (
                  <FilterChip
                    key={c}
                    selected={c === category}
                    onCard
                    onClick={() => setCategory(c)}
                    className={cn(
                      "px-2.5 text-[13px] font-bold",
                      c === category && "bg-brand-soft text-brand-strong",
                    )}
                  >
                    {c}
                  </FilterChip>
                ))}
              </div>
              <span aria-live="polite" className="text-text-sub px-2 text-xs tabular-nums">
                총 {shown.length}건
              </span>
            </div>
            {shown.length === 0 && (
              <p className="text-text-sub px-[24px] py-[20px]">등록된 공지사항이 없어요</p>
            )}
            {shown.map((n) => (
              <button
                key={n.id}
                type="button"
                onClick={() => open(n.id)}
                className="rounded-card bg-surface text-text flex cursor-pointer items-center gap-2 px-4 py-3.5 text-left"
              >
                <span className="flex min-w-0 flex-1 flex-col gap-2">
                  <span className="flex flex-wrap items-center gap-2">
                    {n.pinned && (
                      <span className="rounded-tag bg-check-bg text-check-text px-[7px] py-[2px] text-[12px] font-extrabold">
                        중요
                      </span>
                    )}
                    <span className="text-brand-strong text-[13px] font-bold">{n.category}</span>
                    <span className="flex-1" />
                    <span className="text-text-sub text-[12px]">{n.date}</span>
                  </span>
                  <span className="text-[16px] leading-[1.45] font-bold">{n.title}</span>
                </span>
                <ChevronRight className="text-text-sub shrink-0" size={16} aria-hidden />
              </button>
            ))}
          </section>
        )}
      </main>
    </div>
  );
}
