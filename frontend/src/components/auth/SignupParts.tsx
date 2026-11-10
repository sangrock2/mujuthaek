"use client";

import Link from "next/link";
import { ContactEmailFields } from "@/components/auth/ContactEmailParts";
import { CheckBox } from "@/components/auth/parts";
import { signupTerms, type useSignupForm } from "@/features/auth/useSignupForm";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";

type Form = ReturnType<typeof useSignupForm>;

const termLinks: Partial<Record<(typeof signupTerms)[number]["key"], string>> = {
  tos: routes.terms,
  privacy: routes.privacy,
  marketing: routes.privacy,
};

/** 약관 동의 목록 */
export function TermsList({ form, allClassName }: { form: Form; allClassName?: string }) {
  return (
    <>
      <button
        type="button"
        role="checkbox"
        aria-checked={form.all}
        onClick={form.toggleAll}
        className={cn(
          "border-line-soft text-text flex min-h-[60px] cursor-pointer items-center gap-[12px] border-0 border-b border-solid bg-transparent p-0 text-left",
          allClassName,
        )}
      >
        <CheckBox checked={form.all} />
        <span className="text-[17px] font-extrabold">전체 동의</span>
      </button>
      {signupTerms.map((t) => {
        const on = form.agree[t.key];
        const href = termLinks[t.key];
        return (
          <div key={t.key} className="flex items-center justify-between gap-[8px]">
            <button
              type="button"
              role="checkbox"
              aria-checked={on}
              onClick={() => form.toggle(t.key)}
              className="text-text flex min-h-[48px] flex-1 cursor-pointer items-center gap-[12px] border-0 bg-transparent p-0 text-left"
            >
              <CheckBox checked={on} />
              <span className="text-[15px]">
                <span
                  className={cn("font-bold", t.required ? "text-brand-strong" : "text-text-sub")}
                >
                  {t.required ? "[필수]" : "[선택]"}
                </span>{" "}
                {t.label}
              </span>
            </button>
            {href && (
              <Link
                href={href}
                className="text-text-sub hover:text-text-sub inline-flex min-h-[44px] items-center text-[14px] font-semibold no-underline"
              >
                보기
              </Link>
            )}
          </div>
        );
      })}
    </>
  );
}

/** 어떤 정보를 저장하나요? */
export function StoredInfo({ className }: { className?: string }) {
  return (
    <section
      aria-label="저장하는 정보"
      className={cn("rounded-card bg-surface flex flex-col gap-[12px]", className)}
    >
      <span className="text-[17px] font-extrabold">어떤 정보를 저장하나요?</span>
      <ul className="text-text-sub m-0 flex list-none flex-col gap-[8px] p-0 text-[14px] leading-[1.6]">
        <li>
          계정에는 간편 로그인 회원번호·닉네임, 적었다면 연락용 이메일, 관심 공고·알림 설정만
          저장하고, 탈퇴하면 바로 지워요. 비밀번호는 받지 않아요
        </li>
        <li>입력한 조건은 계정과 상관없이 이 기기에만 30일 동안 저장해요</li>
        <li className="text-brand-strong font-bold">소득·자산은 어디에도 저장하지 않아요</li>
      </ul>
    </section>
  );
}

/** 연락용 이메일 (선택) */
export function SignupEmail({ form, className }: { form: Form; className?: string }) {
  return (
    <section aria-label="연락용 이메일" className={cn("rounded-card bg-surface", className)}>
      <ContactEmailFields
        email={form.email}
        onEmail={form.setEmail}
        consent={form.emailConsent}
        onConsent={form.setEmailConsent}
        error={form.emailError}
      />
    </section>
  );
}

/** 가입 버튼: 필수 약관에 동의하고 이메일(적었다면)이 맞으면 저장한 뒤 가입 완료로 */
export function SignupSubmit({ form, className }: { form: Form; className?: string }) {
  const cls = cn(
    "flex w-full items-center justify-center rounded-[16px] border-0 font-extrabold",
    form.ready ? "bg-brand cursor-pointer text-white" : "bg-line text-text-sub cursor-default",
    className,
  );
  return (
    <button
      type="button"
      aria-disabled={form.ready ? undefined : "true"}
      onClick={form.submit}
      className={cls}
    >
      {form.submitText}
    </button>
  );
}
