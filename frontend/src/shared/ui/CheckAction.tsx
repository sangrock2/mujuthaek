"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CircleAlert } from "lucide-react";

/**
 * 확인 필요 조건의 다음 할 일: 넣을 입력이 있으면 그 화면으로 「입력하고 확인」, 없으면 「원문 확인」
 * (주거·혜택·사업공간·사업 지원 공통. 넣을 화면은 inputHrefOf로 정해요)
 */
export function CheckAction({
  inputHref,
  web,
  onReview,
}: {
  inputHref?: string;
  web: boolean;
  onReview?: () => void;
}) {
  const pathname = usePathname();
  const href =
    inputHref && pathname
      ? `${inputHref}${inputHref.includes("?") ? "&" : "?"}next=${encodeURIComponent(pathname)}`
      : inputHref;
  if (inputHref) {
    return (
      <Link
        href={href!}
        className="bg-check-bg text-check-text hover:text-check-text inline-flex min-h-[40px] flex-none items-center gap-[5px] rounded-[10px] px-[12px] text-[14px] font-bold no-underline"
      >
        {web && <CircleAlert size={17} aria-hidden />}
        입력하고 확인
      </Link>
    );
  }
  if (onReview) {
    return (
      <button
        type="button"
        onClick={onReview}
        className="text-check-text inline-flex min-h-[44px] flex-none cursor-pointer items-center gap-[5px] border-0 bg-transparent text-[14px] font-bold"
      >
        {web && <CircleAlert size={17} aria-hidden />}
        원문 확인
      </button>
    );
  }
  return (
    <span className="text-check-text inline-flex flex-none items-center gap-[5px] text-[14px] font-bold">
      {web && <CircleAlert size={17} aria-hidden />}
      원문 확인
    </span>
  );
}
