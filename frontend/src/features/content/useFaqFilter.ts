import { useState } from "react";
import type { FaqFilter, FaqItem } from "@/mocks/content";

/** FAQ 분류 · 검색 · 펼침 상태 (PC/모바일 공통) */
export function useFaqFilter(items: FaqItem[], initiallyOpen: string[]) {
  const [category, setCategory] = useState<FaqFilter>("전체");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(initiallyOpen.map((id) => [id, true])),
  );

  const q = query.trim();
  const shown = items.filter(
    (d) =>
      (category === "전체" || d.category === category) &&
      (!q || (d.question + d.answer).includes(q)),
  );
  const countText = q ? `‘${q}’ 검색 결과 ${shown.length}개` : `질문 ${shown.length}개`;
  const toggle = (id: string) => setOpen((o) => ({ ...o, [id]: !o[id] }));

  return { category, setCategory, query, setQuery, shown, countText, open, toggle };
}
