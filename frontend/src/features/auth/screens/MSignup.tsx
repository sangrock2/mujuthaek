"use client";

import { X } from "lucide-react";
import {
  SignupEmail,
  SignupLeaveError,
  SignupSubmit,
  StoredInfo,
  TermsList,
} from "@/features/auth/components/SignupParts";
import { useSignupForm, useSignupLeave, type ConsentVersions } from "@/features/auth/useSignupForm";

/** 가입 마무리: 간편 로그인한 뒤 약관 동의 (동의 기록이 없는 계정은 다른 화면에서도 여기로 와요) */
export function MSignup({ versions }: { versions: ConsentVersions }) {
  const form = useSignupForm(versions);
  const leave = useSignupLeave();

  return (
    <div className="bg-bg text-text flex min-h-screen w-full flex-col">
      <header className="border-line-soft bg-surface flex h-[56px] items-center justify-between border-b border-solid pr-[4px] pl-[16px]">
        <h1 className="m-0 text-[18px] font-extrabold">가입 마무리</h1>
        {/* 동의하지 않으면 로그아웃하고 나가요 (로그인한 채로는 어느 화면에서든 이 화면으로 돌아와요) */}
        <button
          type="button"
          aria-label={leave.loggedIn ? "로그아웃하고 나가기" : "나가기"}
          onClick={leave.leave}
          disabled={leave.leaving}
          className="text-text inline-flex size-[44px] cursor-pointer items-center justify-center rounded-sm border-0 bg-transparent p-0 disabled:opacity-60"
        >
          <X size={22} aria-hidden />
        </button>
      </header>

      <main
        id="main-content"
        tabIndex={-1}
        className="flex flex-1 flex-col gap-[12px] px-[16px] pt-[20px] pb-[32px]"
      >
        <SignupLeaveError leave={leave} />
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
