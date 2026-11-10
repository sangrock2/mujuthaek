"use client";

import Link from "next/link";
import { Check } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { useSearchParams } from "next/navigation";
import {
  loginErrorMessage,
  socialLoginUrl,
  socialProviders,
  type SocialProvider,
} from "@/features/auth/social";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";

/** PC 인증 화면 헤더: 로고 + 오른쪽 */
export function AuthWebHeader({ right }: { right?: React.ReactNode }) {
  return (
    <header className="border-line bg-surface border-b border-solid">
      <div className="mx-auto box-border flex min-h-[68px] w-full max-w-[1200px] items-center justify-between gap-[16px] px-[32px]">
        <Link
          href={routes.main}
          aria-label="무주택자들 소개"
          className="text-text hover:text-text inline-flex items-center gap-[9px] no-underline"
        >
          <Logo size={30} />
          <span className="tracking-logo text-[19px] font-extrabold">무주택자들</span>
        </Link>
        {right}
      </div>
    </header>
  );
}

/** 간편 로그인 버튼 (로고 없이 색만). 누르면 백엔드 로그인 시작 주소로 가요 */
export function SocialButtons({
  suffix = "",
  className,
  buttonClassName,
}: {
  /** 버튼 이름 뒤에 붙일 말 (예: "로 계속하기") */
  suffix?: string;
  className?: string;
  buttonClassName?: string;
}) {
  const tone: Record<SocialProvider, string> = {
    kakao: "bg-kakao-bg text-kakao-text hover:text-kakao-text",
    naver: "bg-naver-bg text-naver-text hover:text-naver-text",
    google: "border border-solid border-line bg-surface text-text hover:text-text",
  };
  return (
    <div className={className}>
      {socialProviders.map((p) => (
        <a
          key={p.key}
          href={socialLoginUrl(p.key)}
          className={cn(
            "rounded-control flex min-h-[56px] items-center justify-center text-[16px] font-bold no-underline",
            tone[p.key],
            buttonClassName,
          )}
        >
          {p.name}
          {suffix}
        </a>
      ))}
    </div>
  );
}

/** 로그인 실패 안내 (백엔드가 /login?error=social&reason=…로 돌려보내요) */
export function LoginError() {
  const params = useSearchParams();
  if (params.get("error") !== "social") return null;
  return (
    <p
      role="alert"
      className="rounded-control bg-check-bg text-check-text m-0 px-[16px] py-[12px] text-[15px] font-semibold"
    >
      {loginErrorMessage(params.get("reason"))}
    </p>
  );
}

/** 체크 상자 모양 (24px, 둥글기 7) */
export function CheckBox({ checked }: { checked: boolean }) {
  return (
    <span
      className={cn(
        "flex size-[24px] flex-none items-center justify-center rounded-[7px] text-white",
        checked ? "bg-brand" : "bg-check-off",
      )}
    >
      <Check size={16} strokeWidth={3} aria-hidden />
    </span>
  );
}

/** 라디오 점 (22px) */
export function RadioDot({ checked }: { checked: boolean }) {
  return (
    <span
      className={cn(
        "rounded-pill mt-px box-border size-[22px] flex-none border-solid",
        checked ? "border-brand border-[7px]" : "border-off border-2",
      )}
    />
  );
}

/** 단계 표시 막대 */
export function StepDots({
  step,
  labels,
  className,
  dotClassName,
}: {
  step: number;
  labels: readonly string[];
  className?: string;
  dotClassName?: string;
}) {
  return (
    <ol aria-label="진행 단계" className={cn("m-0 grid list-none gap-[6px] p-0", className)}>
      {labels.map((l, i) => (
        <li
          key={l}
          aria-current={i + 1 === step ? "step" : undefined}
          className={cn(
            "h-[6px] rounded-[3px]",
            i + 1 <= step ? "bg-brand" : "bg-line",
            dotClassName,
          )}
        >
          <span className="sr-only">
            {i + 1}단계 {l}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** 약관 링크 안내 (로그인 아래) */
export function LegalNote() {
  return (
    <span className="text-text-tertiary text-center text-[13px] leading-[1.6]">
      처음 로그인하면{" "}
      <Link href={routes.terms} className="text-text-sub hover:text-text-sub font-semibold">
        이용약관
      </Link>
      과{" "}
      <Link href={routes.privacy} className="text-text hover:text-text font-bold">
        개인정보처리방침
      </Link>
      에 동의를 받아요
    </span>
  );
}
