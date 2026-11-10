"use client";

import Link from "next/link";
import { X } from "lucide-react";
import { SignupEmail, SignupSubmit, StoredInfo, TermsList } from "@/components/auth/SignupParts";
import { useSignupForm } from "@/features/auth/useSignupForm";
import { routes } from "@/lib/routes";

/** 가입 마무리: 처음 간편 로그인한 뒤 약관 동의 */
export function MSignup() {
  const form = useSignupForm();

  return (
    <div className="bg-bg text-text flex min-h-screen w-full flex-col">
      <header className="border-line-soft bg-surface flex h-[56px] items-center justify-between border-b border-solid pr-[4px] pl-[16px]">
        <h1 className="m-0 text-[18px] font-extrabold">가입 마무리</h1>
        {/* 웹의 로고 링크처럼 나갈 수 있게 (동의하지 않으면 관심·알림만 못 써요) */}
        <Link
          href={routes.main}
          aria-label="나가기"
          className="text-text hover:text-text inline-flex size-[44px] items-center justify-center rounded-sm"
        >
          <X size={22} aria-hidden />
        </Link>
      </header>

      <main className="flex flex-1 flex-col gap-[12px] px-[16px] pt-[20px] pb-[32px]">
        <div className="flex flex-col gap-[6px] px-[4px] pb-[4px]">
          <span className="tracking-h1 text-[24px] font-extrabold">약관에 동의해 주세요</span>
          <span className="text-text-sub text-[15px]">
            동의하면 관심 공고와 알림을 쓸 수 있어요
          </span>
        </div>

        <StoredInfo className="p-[20px]" />

        <SignupEmail form={form} className="p-[20px]" />

        <section
          aria-label="약관 동의"
          className="rounded-card bg-surface flex flex-col px-[20px] pt-[8px] pb-[12px]"
        >
          <TermsList form={form} allClassName="min-h-[58px]" />
        </section>
      </main>

      <div className="border-line bg-surface sticky bottom-0 border-t border-solid px-[16px] pt-[12px] pb-[28px]">
        <SignupSubmit form={form} className="min-h-[58px] text-[17px]" />
      </div>
    </div>
  );
}
