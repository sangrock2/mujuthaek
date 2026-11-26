"use client";

import { reportHref } from "@/features/me/tabs";
import Link from "next/link";
import { ChevronDown, ChevronRight, Search } from "lucide-react";
import { WebContentMain, WebContentShell } from "@/features/content/components/WebContentShell";
import { FilterChip } from "@/shared/ui/Chip";
import { useFaq } from "@/features/content/queries";
import { useFaqFilter } from "@/features/content/useFaqFilter";
import { cn } from "@/shared/lib/cn";
import { routes } from "@/shared/lib/routes";
import { faqCategories } from "@/features/content/mocks/content";

export function FaqScreen() {
  const { data } = useFaq();
  const f = useFaqFilter(data.web, data.initiallyOpen);

  return (
    <WebContentShell current={routes.faq}>
      <WebContentMain className="max-w-none gap-0 px-0 pt-0 lg:px-0 lg:pt-0">
        <div className="bg-surface flex flex-col items-center gap-4 px-4 pt-7 pb-6 text-center lg:pt-8 lg:pb-8">
          <h1 className="tracking-h1 m-0 text-[26px] font-extrabold lg:text-[34px]">
            무엇이 궁금한가요?
          </h1>
          <label className="relative flex w-full max-w-[640px]">
            <span className="sr-only">질문 검색</span>
            <Search
              size={18}
              className="text-text-tertiary absolute top-1/2 left-4 -translate-y-1/2"
              aria-hidden
            />
            <input
              type="search"
              value={f.query}
              onChange={(e) => f.setQuery(e.target.value)}
              placeholder="예: 판정, 알림, 탈퇴"
              className="rounded-card bg-fill text-text placeholder:text-text-sub min-h-[52px] min-w-0 flex-1 border-0 pr-4 pl-11 text-base"
            />
          </label>
          <div
            role="group"
            aria-label="질문 분류"
            className="flex flex-wrap justify-center gap-[6px]"
          >
            {faqCategories.map((c) => (
              <FilterChip
                key={c}
                selected={c === f.category}
                onClick={() => f.setCategory(c)}
                onCard
                className={cn(
                  "px-3 text-[13px] font-bold",
                  c === f.category && "bg-brand-soft text-brand-strong",
                )}
              >
                {c}
              </FilterChip>
            ))}
          </div>
        </div>

        <div className="mx-auto flex w-full max-w-[760px] flex-col gap-5 px-4 pt-5 sm:px-6 lg:pt-7">
          <section aria-label="질문 목록" className="flex flex-col gap-2">
            <span aria-live="polite" className="sr-only">
              {f.countText}
            </span>
            {f.shown.map((item) => {
              const open = !!f.open[item.id];
              const panelId = `faq-${item.id}`;
              return (
                <div key={item.id} className="rounded-card bg-surface min-w-0">
                  <button
                    type="button"
                    aria-expanded={open}
                    aria-controls={panelId}
                    onClick={() => f.toggle(item.id)}
                    className="text-text flex min-h-[64px] w-full cursor-pointer items-center gap-3 border-0 bg-transparent px-4 py-3.5 text-left focus-visible:outline-offset-[-3px] sm:px-5"
                  >
                    <span className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1.5">
                      <span
                        className={cn(
                          "rounded-pill px-2.5 py-1 text-xs font-bold",
                          open ? "bg-brand-soft text-brand-strong" : "bg-fill text-text-sub",
                        )}
                      >
                        {item.category}
                      </span>
                      <span className="text-base leading-[1.45] font-bold break-keep">
                        {item.question}
                      </span>
                    </span>
                    <ChevronDown
                      size={20}
                      className={cn("text-text-sub flex-none", open && "rotate-180")}
                      aria-hidden
                    />
                  </button>
                  {open && (
                    <div
                      id={panelId}
                      className="border-line-soft mx-4 flex flex-col gap-2 border-t py-4 sm:mx-5"
                    >
                      <p className="text-text-body-long m-0 text-[16px] leading-[1.75]">
                        {item.answer}
                      </p>
                      {item.link && (
                        <Link
                          href={item.link.href}
                          className="inline-flex min-h-[44px] items-center gap-[2px] self-start text-[15px] font-bold no-underline"
                        >
                          {item.link.label}
                          <ChevronRight size={16} strokeWidth={2.2} aria-hidden />
                        </Link>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
            {f.shown.length === 0 && (
              <div className="bg-surface flex flex-col gap-[6px] rounded-[20px] px-[24px] py-[40px] text-center">
                <span className="text-[17px] font-bold">찾는 질문이 없어요</span>
                <span className="text-text-sub text-[15px]">
                  다른 말로 검색하거나 아래로 문의해 주세요
                </span>
              </div>
            )}
          </section>

          <section
            aria-label="문의"
            className="rounded-card bg-surface flex flex-wrap items-center justify-between gap-4 p-5"
          >
            <span className="flex flex-col gap-[6px]">
              <span className="text-[20px] font-extrabold">답을 못 찾았나요?</span>
              <span className="text-text-sub text-sm">
                {data.contact.email ? data.contact.hours : "문의 채널을 준비하고 있어요"}
              </span>
            </span>
            <span className="flex flex-wrap gap-[8px]">
              {data.contact.email && (
                <a
                  href={`mailto:${data.contact.email}`}
                  className="rounded-pill bg-brand inline-flex min-h-11 items-center px-4 text-sm font-bold text-white no-underline hover:text-white"
                >
                  이메일로 문의
                </a>
              )}
              <Link
                href={reportHref({ kind: "WRONG_INFO", from: "자주 묻는 질문" })}
                className="rounded-pill bg-brand-soft text-brand-strong hover:text-brand-strong inline-flex min-h-11 items-center px-4 text-sm font-bold no-underline"
              >
                정보가 틀렸다면 제보하기
              </Link>
            </span>
          </section>
        </div>
      </WebContentMain>
    </WebContentShell>
  );
}
