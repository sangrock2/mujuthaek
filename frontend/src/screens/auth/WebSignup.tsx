"use client";

import { AuthWebHeader } from "@/components/auth/parts";
import { SignupEmail, SignupSubmit, StoredInfo, TermsList } from "@/components/auth/SignupParts";
import { useSignupForm } from "@/features/auth/useSignupForm";

/** 가입 마무리: 처음 간편 로그인한 뒤 약관 동의 */
export function WebSignup() {
  const form = useSignupForm();

  return (
    <div className="bg-bg text-text flex min-h-screen w-full flex-col">
      <AuthWebHeader />

      <main className="mx-auto box-border flex w-full max-w-[600px] flex-1 flex-col gap-[16px] px-[24px] pt-[48px] pb-[72px]">
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
