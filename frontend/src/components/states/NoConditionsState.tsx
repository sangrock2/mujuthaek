import Link from "next/link";
import { ClipboardList } from "lucide-react";
import { routes } from "@/lib/routes";

const copy = {
  title: "내 조건을 입력하면 받을 수 있는 집과 혜택을 보여드려요",
  body: "로그인하지 않아도 돼요. 모르는 칸은 비워도 되고, 소득·자산은 저장하지 않아요.",
  cta: "내 조건 입력하기",
};

/** 홈 · 아직 조건을 입력하지 않았을 때 (PC) */
export function WebNoConditionsState() {
  return (
    <div className="rounded-card-lg bg-surface flex flex-col items-center gap-[18px] px-[32px] py-[56px] text-center">
      <span className="bg-brand-soft text-brand flex size-[80px] items-center justify-center rounded-[26px]">
        <ClipboardList size={40} strokeWidth={1.6} aria-hidden />
      </span>
      <h2 className="tracking-h1 m-0 max-w-[560px] text-[26px] font-extrabold">{copy.title}</h2>
      <span className="text-text-sub max-w-[520px] text-[16px] leading-[1.6]">{copy.body}</span>
      <Link
        href={routes.profile}
        className="rounded-control bg-brand inline-flex min-h-[52px] items-center px-[22px] text-[16px] font-extrabold text-white no-underline hover:text-white"
      >
        {copy.cta}
      </Link>
    </div>
  );
}

/** 홈 · 아직 조건을 입력하지 않았을 때 (모바일) */
export function MNoConditionsState() {
  return (
    <section className="rounded-card bg-surface flex flex-col items-center gap-[12px] px-[20px] py-[28px] text-center">
      <span className="bg-brand-soft text-brand flex size-[64px] items-center justify-center rounded-[20px]">
        <ClipboardList size={32} aria-hidden />
      </span>
      <h2 className="tracking-title m-0 text-[20px] font-extrabold">{copy.title}</h2>
      <span className="text-text-sub text-[15px] leading-[1.6]">{copy.body}</span>
      <Link
        href={routes.profile}
        className="rounded-control bg-brand flex min-h-[52px] items-center justify-center self-stretch text-[16px] font-extrabold text-white no-underline hover:text-white"
      >
        {copy.cta}
      </Link>
    </section>
  );
}
