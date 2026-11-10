"use client";

import Link from "next/link";
import { ChevronDown, Search } from "lucide-react";
import { MBackHeader } from "@/components/layout/MBackHeader";
import { MPage } from "@/components/layout/Responsive";
import { FilterChip } from "@/components/ui/Chip";
import { useFaq } from "@/features/content/queries";
import { useFaqFilter } from "@/features/content/useFaqFilter";
import { reportHref } from "@/features/me/tabs";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import { faqCategories } from "@/mocks/content";

export function MFaq() {
  const { data } = useFaq();
  // 웹과 같은 질문 목록 (모바일만 줄인 목록은 질문이 빠지고 번호가 달랐어요)
  const f = useFaqFilter(data.web, data.initiallyOpen);

  return (
    <MPage>
      <MBackHeader title="자주 묻는 질문" backHref={routes.me} />
      <main className="flex flex-1 flex-col gap-[12px] px-[16px] pt-[16px] pb-[28px]">
        <label className="relative flex">
          <span className="sr-only">질문 검색</span>
          <span className="text-text-tertiary absolute top-1/2 left-[16px] flex -translate-y-1/2">
            <Search size={20} aria-hidden />
          </span>
          <input
            type="search"
            value={f.query}
            onChange={(e) => f.setQuery(e.target.value)}
            placeholder="예: 판정, 알림, 탈퇴"
            className="rounded-tile bg-surface text-text placeholder:text-text-tertiary min-h-[54px] min-w-0 flex-1 border-0 pr-[16px] pl-[46px] text-[16px]"
          />
        </label>
        <div
          role="group"
          aria-label="질문 분류"
          className="flex gap-[6px] overflow-x-auto pb-[2px]"
        >
          {faqCategories.map((c) => (
            <FilterChip
              key={c}
              selected={c === f.category}
              onClick={() => f.setCategory(c)}
              className="flex-none px-[14px] font-bold"
            >
              {c}
            </FilterChip>
          ))}
        </div>
        <span aria-live="polite" className="text-text-sub px-[4px] text-[13px]">
          {f.countText}
        </span>
        {f.shown.map((item) => {
          const open = !!f.open[item.id];
          const panelId = `mfaq-${item.id}`;
          return (
            <div key={item.id} className="bg-surface overflow-hidden rounded-[18px]">
              <button
                type="button"
                aria-expanded={open}
                aria-controls={panelId}
                onClick={() => f.toggle(item.id)}
                className="text-text flex min-h-[60px] w-full cursor-pointer items-center gap-[10px] border-0 bg-transparent px-[18px] py-[16px] text-left"
              >
                <span className="flex flex-1 flex-col gap-[4px]">
                  <span className="text-brand-strong text-[12px] font-bold">{item.category}</span>
                  <span className="text-[16px] leading-[1.45] font-bold">{item.question}</span>
                </span>
                <ChevronDown
                  size={20}
                  className={cn("text-text-sub flex-none", open && "rotate-180")}
                  aria-hidden
                />
              </button>
              {open && (
                <div id={panelId} className="flex flex-col gap-[8px] px-[18px] pb-[18px]">
                  <p className="text-text-body-long m-0 text-[15px] leading-[1.75]">
                    {item.answer}
                  </p>
                  {item.link && (
                    <Link
                      href={item.link.href}
                      className="inline-flex min-h-[44px] items-center self-start text-[14px] font-bold no-underline"
                    >
                      {item.link.label}
                    </Link>
                  )}
                </div>
              )}
            </div>
          );
        })}
        {f.shown.length === 0 && (
          <div className="bg-surface text-text-sub rounded-[18px] px-[20px] py-[32px] text-center text-[15px]">
            찾는 질문이 없어요. 다른 말로 찾아보거나 아래로 문의해 주세요
          </div>
        )}
        <section
          aria-label="문의"
          className="bg-brand-deep mt-[4px] flex flex-col gap-[10px] rounded-[22px] p-[20px] text-white"
        >
          <span className="text-[17px] font-extrabold">답을 못 찾았나요?</span>
          <span className="text-brand-deep-text text-[14px]">
            {data.contact.hours} · 보통 하루 안에 답해드려요
          </span>
          <a
            href={`mailto:${data.contact.email}`}
            className="rounded-control text-brand-strong hover:text-brand-strong flex min-h-[50px] items-center justify-center bg-white text-[15px] font-extrabold no-underline"
          >
            이메일로 문의
          </a>
          <Link
            href={reportHref({ kind: "WRONG_INFO", from: "자주 묻는 질문" })}
            className="text-brand-deep-text hover:text-brand-deep-text inline-flex min-h-[44px] items-center justify-center text-[14px] font-bold no-underline"
          >
            정보가 틀렸다면 제보하기
          </Link>
        </section>
      </main>
    </MPage>
  );
}
