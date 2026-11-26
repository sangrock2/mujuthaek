"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, ChevronLeft, ChevronRight } from "lucide-react";
import {
  WebContentMain,
  WebContentShell,
  WebContentTitle,
} from "@/features/content/components/WebContentShell";
import { FilterChip } from "@/shared/ui/Chip";
import { useAnnouncements } from "@/features/content/queries";
import { cn } from "@/shared/lib/cn";
import { routes } from "@/shared/lib/routes";
import { announcementCategories, type AnnouncementFilter } from "@/features/content/mocks/content";

export function WebNotices() {
  const { data } = useAnnouncements();
  const [category, setCategory] = useState<AnnouncementFilter>("전체");
  const [selected, setSelected] = useState(data[0]?.id ?? "");
  const list = useRef<HTMLElement>(null);

  // 중요 공지를 맨 위로
  const shown = data
    .filter((d) => category === "전체" || d.category === category)
    .sort((a, b) => Number(b.pinned) - Number(a.pinned));
  const index = Math.max(
    0,
    shown.findIndex((d) => d.id === selected),
  );
  const current = shown[index];
  const move = (step: number) => {
    const next = (index + step + shown.length) % shown.length;
    setSelected(shown[next].id);
    list.current?.querySelectorAll("button")[next]?.scrollIntoView({ block: "nearest" });
  };

  return (
    <WebContentShell
      current={routes.announcements}
      className="h-dvh min-h-0 overflow-hidden [&>footer]:shrink-0 [&>footer>div]:py-2.5 [&>header]:shrink-0"
    >
      <WebContentMain className="min-h-0 gap-[16px] py-[20px]">
        <div className="shrink-0">
          <WebContentTitle title="공지사항" sub="새 기능, 점검, 정책 변경 소식을 알려드려요" />
        </div>
        <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,5fr)_minmax(0,7fr)] gap-5">
          <div className="flex min-h-0 min-w-0 flex-col gap-2">
            <div className="rounded-card bg-surface flex shrink-0 flex-wrap items-center justify-between gap-x-2 px-2 py-1">
              <div
                role="group"
                aria-label="공지 종류"
                className="flex flex-wrap items-center gap-1"
              >
                {announcementCategories.map((c) => (
                  <FilterChip
                    key={c}
                    selected={c === category}
                    onClick={() => {
                      list.current?.scrollTo(0, 0);
                      setCategory(c);
                    }}
                    onCard
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
            <section
              ref={list}
              aria-label="공지 목록"
              tabIndex={0}
              className="rounded-card min-h-0 min-w-0 overflow-y-auto overscroll-contain"
            >
              <div className="flex min-w-0 flex-col gap-2 p-0.5">
                {shown.length === 0 && (
                  <p className="text-text-sub px-[24px] py-[20px]">등록된 공지사항이 없어요</p>
                )}
                {shown.map((n) => {
                  const on = n.id === current?.id;
                  return (
                    <button
                      key={n.id}
                      type="button"
                      aria-pressed={on}
                      onClick={() => setSelected(n.id)}
                      className={cn(
                        "rounded-card text-text grid w-full cursor-pointer grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-2 border px-4 py-3.5 text-left focus-visible:outline-offset-[-3px]",
                        on
                          ? "border-brand/45 bg-brand-soft"
                          : "bg-surface hover:border-line border-transparent",
                      )}
                    >
                      <span className="flex min-w-0 flex-wrap items-center gap-1.5">
                        <span className="text-brand-strong text-[12px] font-extrabold">
                          {n.category}
                        </span>
                        {n.pinned && (
                          <span className="rounded-tag bg-check-bg text-check-text px-1.5 py-0.5 text-[11px] font-bold">
                            중요
                          </span>
                        )}
                      </span>
                      <span className="text-text-sub text-right text-[12px] whitespace-nowrap tabular-nums">
                        {n.date}
                      </span>
                      <span className="min-w-0 text-[15px] leading-[1.45] font-bold break-keep">
                        {n.title}
                      </span>
                      <ChevronRight
                        size={16}
                        aria-hidden
                        className={cn(
                          "justify-self-end",
                          on ? "text-brand-strong" : "text-text-tertiary",
                        )}
                      />
                    </button>
                  );
                })}
              </div>
            </section>
          </div>

          {current && (
            <article
              key={current.id}
              aria-label="공지 상세"
              aria-live="polite"
              tabIndex={0}
              className="rounded-card-lg bg-surface max-h-full min-h-0 min-w-0 self-start overflow-y-auto overscroll-contain px-8 py-7 [overflow-wrap:anywhere]"
            >
              <div className="flex min-w-0 flex-col gap-[20px]">
                <div className="border-line-soft flex flex-col gap-[10px] border-b border-solid pb-[20px]">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="rounded-badge bg-brand-soft text-brand-strong px-[10px] py-[4px] text-[13px] font-bold">
                      {current.category}
                    </span>
                    {current.pinned && (
                      <span className="rounded-badge bg-check-bg text-check-text px-[10px] py-[4px] text-[13px] font-bold">
                        중요
                      </span>
                    )}
                    <span className="text-text-sub ml-auto text-xs tabular-nums">
                      {index + 1} / {shown.length}번째 공지
                    </span>
                  </div>
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
                <div className="border-line-soft flex flex-wrap items-center justify-between gap-2 border-t pt-4">
                  {current.cta && (
                    <Link
                      href={current.cta.href}
                      className="rounded-pill bg-brand inline-flex min-h-11 items-center gap-[6px] self-start px-[20px] text-[16px] font-extrabold text-white no-underline hover:text-white"
                    >
                      {current.cta.label}
                      <ArrowRight size={18} strokeWidth={2.2} aria-hidden />
                    </Link>
                  )}
                  {shown.length > 1 && (
                    <div className="ml-auto flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => move(-1)}
                        className="rounded-pill bg-fill text-text-sub hover:bg-brand-soft inline-flex min-h-11 cursor-pointer items-center gap-1 px-3 text-sm font-semibold"
                      >
                        <ChevronLeft size={18} aria-hidden />
                        이전 공지
                      </button>
                      <button
                        type="button"
                        onClick={() => move(1)}
                        className="rounded-pill bg-fill text-text-sub hover:bg-brand-soft inline-flex min-h-11 cursor-pointer items-center gap-1 px-3 text-sm font-semibold"
                      >
                        다음 공지
                        <ChevronRight size={18} aria-hidden />
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </article>
          )}
        </div>
      </WebContentMain>
    </WebContentShell>
  );
}
