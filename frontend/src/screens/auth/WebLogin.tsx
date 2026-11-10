"use client";

import { Suspense } from "react";
import Link from "next/link";
import { BellRing, ChevronRight, Heart, ListChecks } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { LegalNote, LoginError, SocialButtons } from "@/components/auth/parts";
import { useLeaveIfLoggedIn } from "@/features/auth/session";
import { routes } from "@/lib/routes";

const perks = [
  { icon: Heart, title: "관심 공고 저장", desc: "어느 기기에서든 이어서 볼 수 있어요" },
  {
    icon: BellRing,
    title: "새 공고 · 마감 알림",
    desc: "내 조건에 맞는 공고가 나오면 바로 알려드려요",
  },
  {
    icon: ListChecks,
    title: "조건은 한 번만",
    desc: "로그인하지 않아도 이 기기에 30일 동안 저장해 둬요",
  },
];

export function WebLogin() {
  useLeaveIfLoggedIn();
  return (
    <div className="bg-surface text-text flex min-h-screen w-full flex-wrap">
      <section
        aria-label="무주택자들 소개"
        className="bg-brand-deep box-border flex min-w-0 flex-col justify-between gap-[48px] px-[56px] py-[48px] text-white"
        style={{ flex: "1 1 480px" }}
      >
        <Link
          href={routes.main}
          aria-label="무주택자들 소개"
          className="inline-flex items-center gap-[10px] self-start text-white no-underline hover:text-white"
        >
          <Logo size={34} inverted />
          <span className="tracking-logo text-[22px] font-extrabold">무주택자들</span>
        </Link>
        <div className="flex flex-col gap-[32px]">
          <h1 className="tracking-h1 m-0 text-[40px] leading-[1.3] font-extrabold">
            로그인하면
            <br />
            마감을 놓치지 않아요
          </h1>
          <ul className="m-0 flex list-none flex-col gap-[20px] p-0">
            {perks.map(({ icon: Icon, title, desc }) => (
              <li key={title} className="flex items-center gap-[14px]">
                <span className="rounded-control text-brand-deep-text-2 flex size-[44px] flex-none items-center justify-center bg-white/10">
                  <Icon size={22} aria-hidden />
                </span>
                <span className="flex flex-col gap-[2px]">
                  <span className="text-[17px] font-bold">{title}</span>
                  <span className="text-brand-deep-text-2 text-[15px]">{desc}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
        <span className="text-brand-deep-text-2 text-[14px]">
          로그인하지 않아도 판정 결과는 볼 수 있어요
        </span>
      </section>

      <main
        className="box-border flex min-w-0 items-center justify-center px-[32px] py-[48px]"
        style={{ flex: "1 1 520px" }}
      >
        <div className="flex w-full max-w-[420px] flex-col gap-[24px]">
          <div className="flex flex-col gap-[8px]">
            <h2 className="tracking-h1 m-0 text-[30px] font-extrabold">로그인</h2>
            <span className="text-text-sub text-[16px]">간편하게 3초면 시작할 수 있어요</span>
          </div>

          <Suspense fallback={null}>
            <LoginError />
          </Suspense>

          <SocialButtons suffix="로 계속하기" className="flex flex-col gap-[10px]" />

          <span className="text-text-sub text-center text-[15px] leading-[1.6]">
            처음이면 간편 로그인으로 바로 가입돼요
            <br />
            비밀번호는 만들지 않아요
          </span>

          <Link
            href={routes.profile}
            className="rounded-control bg-fill text-text hover:text-text flex min-h-[52px] items-center justify-center gap-[4px] text-[15px] font-bold no-underline"
          >
            로그인 없이 계속하기
            <ChevronRight size={18} aria-hidden />
          </Link>

          <LegalNote />
        </div>
      </main>
    </div>
  );
}
