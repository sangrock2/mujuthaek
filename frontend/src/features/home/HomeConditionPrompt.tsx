import Link from "next/link";
import { ArrowRight, SlidersHorizontal } from "lucide-react";
import { routes } from "@/shared/lib/routes";

export function HomeConditionPrompt() {
  return (
    <section
      aria-labelledby="condition-prompt-title"
      className="rounded-card border-line-soft bg-surface flex flex-col items-start gap-[10px] border p-[15px] sm:flex-row sm:items-center sm:gap-[14px] sm:p-[19px]"
    >
      <div className="flex min-w-0 flex-1 items-center gap-[10px]">
        <span className="rounded-control bg-brand-soft text-brand-strong flex size-[41px] shrink-0 items-center justify-center">
          <SlidersHorizontal size={20} aria-hidden />
        </span>
        <div className="flex min-w-0 flex-col gap-[3px]">
          <h2 id="condition-prompt-title" className="m-0 text-[16px] font-extrabold sm:text-[19px]">
            내 조건으로 신청 자격 확인하기
          </h2>
          <p className="text-text-sub m-0 text-[13px] leading-relaxed sm:text-[14px]">
            아는 항목만 입력하면 공고별 자격과 주거 혜택을 확인할 수 있어요.
          </p>
        </div>
      </div>
      <Link
        href={routes.profile}
        className="rounded-control bg-brand hover:bg-brand-strong inline-flex min-h-[44px] shrink-0 items-center gap-[5px] px-[13px] text-[14px] font-bold text-white no-underline hover:text-white"
      >
        내 조건 입력하기 <ArrowRight size={16} aria-hidden />
      </Link>
    </section>
  );
}
