"use client";

import { reportHref } from "@/features/me/tabs";
import Link from "next/link";
import { CircleAlert, RefreshCw, TriangleAlert } from "lucide-react";
import { SERVICE_HOURS } from "@/lib/api/availability";

type LoadErrorProps = {
  title?: string;
  /** 없으면 페이지를 다시 불러와요 */
  onRetry?: () => void;
  /** 예: E-503 */
  code?: string;
  /** 예: 10월 19일 14:32 */
  at?: string;
};

const reload = () => window.location.reload();

function ErrorMeta({ code, at, className }: { code?: string; at?: string; className: string }) {
  if (!code && !at) return null;
  return (
    <span className={className}>
      {[code && `오류 코드 ${code}`, at].filter(Boolean).join(" · ")}
    </span>
  );
}

/** 2 · 데이터를 불러오지 못했을 때 (PC) */
export function WebLoadErrorState({
  title = "공고를 불러오지 못했어요",
  onRetry = reload,
  code,
  at,
}: LoadErrorProps) {
  return (
    <div
      role="alert"
      className="bg-bg rounded-card-lg flex flex-col items-center gap-[16px] px-[32px] py-[48px] text-center"
    >
      <span className="bg-surface text-text-sub flex size-[80px] items-center justify-center rounded-[26px]">
        <CircleAlert size={40} strokeWidth={1.6} aria-hidden />
      </span>
      <h2 className="tracking-h1 m-0 text-[26px] font-extrabold">{title}</h2>
      <span className="text-text-sub max-w-[520px] text-[16px] leading-[1.6]">
        잠시 후 다시 시도해 주세요. 계속 안 되면 알려주시면 바로 확인할게요.
        <br />
        서비스 운영 시간: {SERVICE_HOURS}
      </span>
      <div className="flex flex-wrap justify-center gap-[8px]">
        <button
          type="button"
          onClick={onRetry}
          className="rounded-control bg-text inline-flex min-h-[52px] cursor-pointer items-center gap-[6px] border-0 px-[22px] text-[16px] font-extrabold text-white"
        >
          <RefreshCw size={18} strokeWidth={2.2} aria-hidden />
          다시 시도
        </button>
        <Link
          href={reportHref({ kind: "APP_ERROR", from: "오류 화면", code })}
          className="rounded-control bg-surface text-text hover:text-text inline-flex min-h-[52px] items-center px-[20px] text-[16px] font-bold no-underline"
        >
          문제 알리기
        </Link>
      </div>
      <ErrorMeta code={code} at={at} className="text-text-sub text-[13px]" />
    </div>
  );
}

/** 2 · 불러오지 못했을 때 (모바일) */
export function MLoadErrorState({
  title = "공고를 불러오지 못했어요",
  onRetry = reload,
  code,
  at,
}: LoadErrorProps) {
  return (
    <section
      role="alert"
      className="rounded-card bg-surface flex flex-col items-center gap-[12px] px-[20px] py-[28px] text-center"
    >
      <span className="bg-danger-bg text-danger-text flex size-[64px] items-center justify-center rounded-[20px]">
        <TriangleAlert size={32} aria-hidden />
      </span>
      <h2 className="m-0 text-[20px] font-extrabold">{title}</h2>
      <span className="text-text-sub text-[15px] leading-[1.6]">
        잠시 후 다시 시도해 주세요.
        <br />
        서비스 운영 시간: {SERVICE_HOURS}
      </span>
      <button
        type="button"
        onClick={onRetry}
        className="rounded-control bg-brand min-h-[52px] cursor-pointer self-stretch border-0 text-[16px] font-extrabold text-white"
      >
        다시 시도
      </button>
      <ErrorMeta code={code} at={at} className="text-text-sub text-[12px]" />
    </section>
  );
}
