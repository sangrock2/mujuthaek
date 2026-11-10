"use client";

import { useState } from "react";
import Link from "next/link";
import { MBackHeader } from "@/components/layout/MBackHeader";
import { FilterChip } from "@/components/ui/Chip";
import { useAnnouncements } from "@/features/content/queries";
import { routes } from "@/lib/routes";
import { announcementCategories, type AnnouncementFilter } from "@/mocks/content";

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
    <div className="bg-surface text-text flex min-h-screen w-full flex-col">
      <MBackHeader title="공지사항" backHref={routes.me} />
      <main className="flex flex-1 flex-col pt-[12px] pb-[24px]">
        {current ? (
          <article className="flex flex-col gap-[16px] px-[20px] py-[8px]">
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
          <div className="flex flex-col">
            <div role="group" aria-label="공지 종류" className="flex gap-[6px] px-[16px] pb-[8px]">
              {announcementCategories.map((c) => (
                <FilterChip
                  key={c}
                  selected={c === category}
                  onCard
                  onClick={() => setCategory(c)}
                  className="min-h-[38px] px-[14px] font-bold"
                >
                  {c}
                </FilterChip>
              ))}
            </div>
            {shown.map((n) => (
              <button
                key={n.id}
                type="button"
                onClick={() => open(n.id)}
                className="border-line-soft bg-surface text-text flex cursor-pointer flex-col gap-[6px] border-0 border-b border-solid px-[20px] py-[16px] text-left"
              >
                <span className="flex w-full items-center gap-[8px]">
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
              </button>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
