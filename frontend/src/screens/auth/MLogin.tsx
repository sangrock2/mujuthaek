"use client";

import { Suspense } from "react";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { LegalNote, LoginError, SocialButtons } from "@/components/auth/parts";
import { useLeaveIfLoggedIn } from "@/features/auth/session";
import { routes } from "@/lib/routes";

export function MLogin() {
  useLeaveIfLoggedIn();
  return (
    <div className="bg-surface text-text flex min-h-screen w-full flex-col">
      <header className="flex h-[56px] items-center px-[8px]">
        <Link
          href={routes.main}
          aria-label="뒤로"
          className="text-text hover:text-text inline-flex size-[44px] items-center justify-center rounded-sm"
        >
          <ChevronLeft size={24} aria-hidden />
        </Link>
      </header>

      <main className="flex flex-1 flex-col gap-[22px] px-[20px] pt-[12px] pb-[40px]">
        <div className="flex flex-col gap-[14px]">
          <Logo size={44} />
          <h1 className="tracking-h1 m-0 text-[28px] leading-[1.35] font-extrabold">
            로그인하면
            <br />
            마감을 놓치지 않아요
          </h1>
          <span className="text-text-sub text-[15px]">관심 공고 저장 · 새 공고 알림</span>
        </div>

        <Suspense fallback={null}>
          <LoginError />
        </Suspense>

        <SocialButtons suffix="로 계속하기" className="flex flex-col gap-[10px]" />

        <span className="text-text-sub text-center text-[14px] leading-[1.6]">
          처음이면 간편 로그인으로 바로 가입돼요 · 비밀번호는 만들지 않아요
        </span>

        <Link
          href={routes.profile}
          className="rounded-control bg-fill text-text hover:text-text flex min-h-[52px] items-center justify-center text-[15px] font-bold no-underline"
        >
          로그인 없이 계속하기
        </Link>
        <LegalNote />
      </main>
    </div>
  );
}
