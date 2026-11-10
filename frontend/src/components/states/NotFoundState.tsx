import Link from "next/link";
import { Search } from "lucide-react";
import { routes } from "@/lib/routes";

/** 3 · 없는 페이지 (404, PC) */
export function WebNotFoundState() {
  return (
    <div className="rounded-card-lg bg-surface flex flex-col items-center gap-[16px] px-[32px] py-[56px] text-center">
      <span className="text-brand-soft text-[88px] leading-none font-extrabold tracking-[-0.06em] [-webkit-text-stroke:2px_var(--color-brand)]">
        404
      </span>
      <h2 className="tracking-h1 m-0 text-[26px] font-extrabold">찾는 페이지가 없어요</h2>
      <span className="text-text-sub max-w-[520px] text-[16px] leading-[1.6]">
        주소가 바뀌었거나, 마감된 공고라 내려갔을 수 있어요.
      </span>
      <div className="flex flex-wrap justify-center gap-[8px]">
        <Link
          href={routes.home}
          className="rounded-control bg-brand inline-flex min-h-[52px] items-center px-[22px] text-[16px] font-extrabold text-white no-underline hover:text-white"
        >
          홈으로
        </Link>
        <Link
          href={routes.search}
          className="rounded-control bg-fill text-text hover:text-text inline-flex min-h-[52px] items-center gap-[6px] px-[20px] text-[16px] font-bold no-underline"
        >
          <Search size={18} aria-hidden />
          공고 검색하기
        </Link>
      </div>
    </div>
  );
}

/** 3 · 없는 페이지 (모바일) */
export function MNotFoundState() {
  return (
    <section className="rounded-card bg-surface flex flex-col items-center gap-[12px] px-[20px] py-[28px] text-center">
      <span className="tracking-h1 text-brand text-[44px] font-extrabold">404</span>
      <h2 className="m-0 text-[20px] font-extrabold">찾는 페이지가 없어요</h2>
      <span className="text-text-sub text-[15px] leading-[1.6]">
        주소가 바뀌었거나, 마감된 공고라 내려갔을 수 있어요.
      </span>
      <div className="grid grid-cols-2 gap-[8px] self-stretch">
        <Link
          href={routes.home}
          className="rounded-control bg-brand flex min-h-[52px] items-center justify-center text-[15px] font-extrabold text-white no-underline hover:text-white"
        >
          홈으로
        </Link>
        <Link
          href={routes.search}
          className="rounded-control bg-fill text-text hover:text-text flex min-h-[52px] items-center justify-center text-[15px] font-bold no-underline"
        >
          공고 검색
        </Link>
      </div>
    </section>
  );
}
