"use client";

import { AuthWebHeader } from "@/features/auth/components/parts";
import {
  SignupEmail,
  SignupLeaveButton,
  SignupLeaveError,
  SignupSubmit,
  StoredInfo,
  TermsList,
} from "@/features/auth/components/SignupParts";
import { useSignupForm, useSignupLeave, type ConsentVersions } from "@/features/auth/useSignupForm";

/** 가입 마무리: 간편 로그인한 뒤 약관 동의 (동의 기록이 없는 계정은 다른 화면에서도 여기로 와요) */
export function WebSignup({ versions }: { versions: ConsentVersions }) {
  const form = useSignupForm(versions);
  const leave = useSignupLeave();

  return (
    <div className="bg-bg text-text flex min-h-screen w-full flex-col">
      <AuthWebHeader right={<SignupLeaveButton leave={leave} />} />

      <main
        id="main-content"
        tabIndex={-1}
        className="mx-auto box-border flex w-full max-w-[600px] flex-1 flex-col gap-[16px] px-[24px] pt-[48px] pb-[72px]"
      >
        <SignupLeaveError leave={leave} />
        <div className="flex flex-col gap-[8px] px-[4px] pb-[8px]">
          <h1 className="tracking-h1 m-0 text-[32px] font-extrabold">가입을 마무리해 주세요</h1>
          <span className="text-text-sub text-[16px]">
            약관에 동의하면 관심 공고와 알림을 쓸 수 있어요
          </span>
        </div>

        <StoredInfo className="p-[24px]" />

        <SignupEmail form={form} className="p-[24px]" />

        <section
          aria-label="약관 동의"
          className="rounded-card bg-surface flex flex-col px-[24px] pt-[12px] pb-[16px]"
        >
          <TermsList form={form} />
        </section>

        <SignupSubmit form={form} className="min-h-[60px] text-[18px]" />
      </main>
    </div>
  );
}
