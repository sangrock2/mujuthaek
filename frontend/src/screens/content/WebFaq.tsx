"use client";

import { reportHref } from "@/features/me/tabs";
import Link from "next/link";
import { ChevronDown, ChevronRight, Search } from "lucide-react";
import { WebContentMain, WebContentShell } from "@/components/content/WebContentShell";
import { FilterChip } from "@/components/ui/Chip";
import { useFaq } from "@/features/content/queries";
import { useFaqFilter } from "@/features/content/useFaqFilter";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import { faqCategories } from "@/mocks/content";

export function WebFaq() {
  const { data } = useFaq();
  const f = useFaqFilter(data.web, data.initiallyOpen);

  return (
    <WebContentShell current={routes.faq}>
      <WebContentMain className="max-w-[960px] pt-[48px]">
        <div className="flex flex-col items-center gap-[18px] text-center">
          <h1 className="tracking-h1 m-0 text-[34px] font-extrabold">무엇이 궁금한가요?</h1>
          <label className="relative flex w-full max-w-[640px]">
            <span className="sr-only">질문 검색</span>
            <Search
              size={22}
              className="text-text-tertiary absolute top-1/2 left-[20px] -translate-y-1/2"
              aria-hidden
            />
            <input
              type="search"
              value={f.query}
              onChange={(e) => f.setQuery(e.target.value)}
              placeholder="예: 판정, 알림, 탈퇴"
              className="bg-surface text-text placeholder:text-text-tertiary min-h-[64px] min-w-0 flex-1 rounded-[18px] border-0 pr-[20px] pl-[54px] text-[18px] shadow-[0_4px_16px_rgba(25,31,40,0.06)]"
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
                className="min-h-[42px] text-[15px] font-bold"
              >
                {c}
              </FilterChip>
            ))}
          </div>
        </div>

        <section aria-label="질문 목록" className="flex flex-col gap-[10px]">
          <span aria-live="polite" className="text-text-sub text-[14px]">
            {f.countText}
          </span>
          {f.shown.map((item) => {
            const open = !!f.open[item.id];
            const panelId = `faq-${item.id}`;
            return (
              <div key={item.id} className="bg-surface overflow-hidden rounded-[20px]">
                <button
                  type="button"
                  aria-expanded={open}
                  aria-controls={panelId}
                  onClick={() => f.toggle(item.id)}
                  className="text-text flex min-h-[64px] w-full cursor-pointer items-center gap-[14px] border-0 bg-transparent px-[24px] py-[20px] text-left"
                >
                  <span className="text-brand-strong min-w-[74px] flex-none text-[13px] font-bold">
                    {item.category}
                  </span>
                  <span className="flex-1 text-[17px] leading-[1.45] font-bold">
                    {item.question}
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
                    className="flex flex-col gap-[12px] pr-[24px] pb-[22px] pl-[112px]"
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
          className="rounded-card-lg bg-brand-deep flex flex-wrap items-center justify-between gap-[16px] px-[32px] py-[28px] text-white"
        >
          <span className="flex flex-col gap-[6px]">
            <span className="text-[20px] font-extrabold">답을 못 찾았나요?</span>
            <span className="text-brand-deep-text text-[15px]">
              {data.contact.hours} · 보통 하루 안에 답해드려요
            </span>
          </span>
          <span className="flex flex-wrap gap-[8px]">
            <a
              href={`mailto:${data.contact.email}`}
              className="rounded-control text-brand-strong hover:text-brand-strong inline-flex min-h-[52px] items-center bg-white px-[20px] text-[16px] font-extrabold no-underline"
            >
              이메일로 문의
            </a>
            <Link
              href={reportHref({ kind: "WRONG_INFO", from: "자주 묻는 질문" })}
              className="rounded-control inline-flex min-h-[52px] items-center bg-white/12 px-[18px] text-[15px] font-bold text-white no-underline hover:text-white"
            >
              정보가 틀렸다면 제보하기
            </Link>
          </span>
        </section>
      </WebContentMain>
    </WebContentShell>
  );
}
