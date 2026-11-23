"use client";

import { ChevronDown, ChevronRight, FileText } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { reviewAnchorId, type PdfReviewItem } from "@/features/notice/pdfReview";
import { cn } from "@/shared/lib/cn";

export function PdfReviewLink({ id, open }: { id: string; open: (id: string) => void }) {
  return (
    <a
      href={`#${encodeURIComponent(reviewAnchorId(id))}`}
      className="text-brand-strong hover:bg-brand-soft focus-visible:outline-brand inline-flex min-h-[40px] w-fit shrink-0 items-center gap-1 rounded-sm px-2 text-[13px] font-bold"
      onClick={(event) => {
        event.preventDefault();
        open(id);
      }}
    >
      <FileText size={14} aria-hidden />
      원문 확인
    </a>
  );
}

export function PdfReviewList({
  items,
  selected,
  highlighted,
  missed,
  onPick,
}: {
  items: PdfReviewItem[];
  selected?: string;
  highlighted: boolean;
  missed: boolean;
  onPick: (id: string) => void;
}) {
  const [expandedFor, setExpandedFor] = useState<string | null>();
  const [pickedGroup, setPickedGroup] = useState<string>();
  const toggle = useRef<HTMLButtonElement>(null);
  const current = items.find((item) => item.id === selected);
  const groupOf = (item: PdfReviewItem) => (item.group ? `target/${item.group.id}` : "notice");
  const groups = new Map(
    items.map((item) => [groupOf(item), item.group?.label ?? "공고에서 확인 중"]),
  );
  const currentGroup = current ? groupOf(current) : groups.keys().next().value;
  const group = pickedGroup && groups.has(pickedGroup) ? pickedGroup : currentGroup;
  const expanded = expandedFor === (selected ?? null);
  const shown = items.filter((item) => groupOf(item) === group);

  useEffect(() => {
    if (selected) toggle.current?.focus({ preventScroll: true });
  }, [selected]);

  return (
    <section aria-label="원문에서 확인할 항목" className="border-line-soft border-b px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h2
            id={current ? reviewAnchorId(current.id) : undefined}
            className="text-text line-clamp-2 text-[14px] font-extrabold"
          >
            {current?.label ?? "원문에서 확인할 항목"}
          </h2>
          {current && (
            <p className="text-text-sub mt-0.5 text-[12px]" role="status">
              {current.location
                ? [
                    `${current.location.page}쪽`,
                    highlighted && "근거 문장 강조됨",
                    missed && "문장 위치 미확인",
                  ]
                    .filter(Boolean)
                    .join(" · ")
                : "정확한 위치 미확인"}
            </p>
          )}
        </div>
        <button
          ref={toggle}
          type="button"
          aria-expanded={expanded}
          className="bg-fill text-brand-strong flex min-h-[40px] shrink-0 cursor-pointer items-center gap-1 rounded-sm px-2.5 text-[13px] font-bold"
          onClick={() => {
            setPickedGroup(currentGroup);
            setExpandedFor(expanded ? undefined : (selected ?? null));
          }}
        >
          {expanded ? "목록 닫기" : "확인 목록"}
          <ChevronDown size={14} aria-hidden className={cn(expanded && "rotate-180")} />
        </button>
      </div>
      {expanded && (
        <div className="mt-2 flex flex-col gap-2">
          {groups.size > 1 && (
            <select
              aria-label="확인 항목 분류"
              className="bg-fill text-text w-full rounded-sm px-2 py-2 text-[13px] font-semibold"
              value={group}
              onChange={(event) => setPickedGroup(event.target.value)}
            >
              {[...groups].map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          )}
          <ul className="max-h-[28dvh] list-none space-y-1 overflow-y-auto">
            {shown.map((item) => (
              <li key={item.id} id={item.id !== selected ? reviewAnchorId(item.id) : undefined}>
                <button
                  type="button"
                  aria-current={item.id === selected ? "true" : undefined}
                  onClick={() => {
                    setExpandedFor(undefined);
                    onPick(item.id);
                    toggle.current?.focus({ preventScroll: true });
                  }}
                  className={cn(
                    "flex min-h-[40px] w-full cursor-pointer items-center gap-2 rounded-sm px-2 text-left text-[13px]",
                    item.id === selected ? "bg-brand-soft text-brand-strong" : "hover:bg-fill",
                  )}
                >
                  <span className="line-clamp-2 flex-1">{item.label}</span>
                  <span className="text-text-sub shrink-0">
                    {item.location ? `${item.location.page}쪽` : "위치 미확인"}
                  </span>
                  <ChevronRight size={13} aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
