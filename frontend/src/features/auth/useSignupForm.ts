"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { contactEmailError, isEmail, useSaveContactEmail } from "@/features/auth/contactEmail";
import { routes } from "@/lib/routes";

export const signupTerms = [
  { key: "age", required: true, label: "만 14세 이상이에요" },
  { key: "tos", required: true, label: "이용약관 동의" },
  { key: "privacy", required: true, label: "개인정보 수집·이용 동의" },
  { key: "alert", required: false, label: "공고·마감 알림 받기" },
  { key: "marketing", required: false, label: "이벤트·소식 받기" },
] as const;

export type TermKey = (typeof signupTerms)[number]["key"];

const initialAgree: Record<TermKey, boolean> = {
  age: false,
  tos: false,
  privacy: false,
  alert: true,
  marketing: false,
};

/** 가입 마무리(약관 동의 + 연락용 이메일(선택)) 화면 상태 (PC/모바일 공통) */
export function useSignupForm() {
  const router = useRouter();
  const [agree, setAgree] = useState(initialAgree);
  const [email, setEmail] = useState("");
  const [emailConsent, setEmailConsent] = useState(false);
  const saveEmail = useSaveContactEmail();

  const all = signupTerms.every((t) => agree[t.key]);
  const requiredOk = signupTerms.filter((t) => t.required).every((t) => agree[t.key]);
  // 이메일은 선택: 비워 두거나, 적었다면 형식이 맞고 수집·이용에 동의해야 해요
  const emailOk = email.trim() === "" || (isEmail(email) && emailConsent);
  const ready = requiredOk && emailOk && !saveEmail.isPending;

  return {
    agree,
    all,
    ready,
    email,
    setEmail,
    emailConsent,
    setEmailConsent,
    emailError: saveEmail.isError ? contactEmailError(saveEmail.error) : undefined,
    /** 이메일을 적었으면 먼저 저장하고(실패하면 이 화면에 남아요) 가입 완료로 */
    submit: () => {
      if (!ready) return;
      if (email.trim() === "") {
        router.push(routes.welcome);
        return;
      }
      saveEmail.mutate(email, { onSuccess: () => router.push(routes.welcome) });
    },
    toggle: (key: TermKey) => setAgree((a) => ({ ...a, [key]: !a[key] })),
    toggleAll: () =>
      setAgree(
        Object.fromEntries(signupTerms.map((t) => [t.key, !all])) as Record<TermKey, boolean>,
      ),
    // 백엔드 동의 기록(POST /api/v1/me/consents)이 생기면 여기서 보내요
    submitText: !requiredOk
      ? "필수 약관에 동의해 주세요"
      : !emailOk
        ? "이메일을 확인해 주세요"
        : saveEmail.isPending
          ? "저장하는 중"
          : "동의하고 시작하기",
  };
}
