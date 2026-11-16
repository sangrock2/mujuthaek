"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { contactEmailError, isEmail, useSaveContactEmail } from "@/features/auth/contactEmail";
import { sessionKey, useLogout, useSession, type Session } from "@/features/auth/session";
import { api, ApiError } from "@/shared/lib/api/client";
import { USE_MOCKS } from "@/shared/lib/api/config";
import { endpoints } from "@/shared/lib/api/endpoints";
import { routes } from "@/shared/lib/routes";

export const signupTerms = [
  { key: "age", required: true, label: "만 14세 이상이에요" },
  { key: "tos", required: true, label: "이용약관 동의" },
  { key: "privacy", required: true, label: "개인정보 수집·이용 동의" },
  { key: "alert", required: false, label: "공고·마감 알림 받기" },
  { key: "marketing", required: false, label: "이벤트·소식 받기" },
] as const;

export type TermKey = (typeof signupTerms)[number]["key"];

/** 동의 화면이 링크하는 지금 이용약관·개인정보처리방침의 버전 (서버 화면이 문서에서 읽어 넘겨요) */
export type ConsentVersions = { terms: string; privacy: string };

// 선택 항목은 미리 체크하지 않아요 (미리 체크한 선택 동의는 동의로 보지 않아요)
const initialAgree: Record<TermKey, boolean> = {
  age: false,
  tos: false,
  privacy: false,
  alert: false,
  marketing: false,
};

function termsError(error: unknown) {
  if (error instanceof ApiError && error.status === 401) {
    return "로그인이 끝났어요. 다시 로그인한 뒤 동의해 주세요";
  }
  return "동의를 저장하지 못했어요. 잠시 뒤 다시 시도해 주세요";
}

/** 가입 마무리(약관 동의 + 연락용 이메일(선택)) 화면 상태 (PC/모바일 공통) */
export function useSignupForm(versions: ConsentVersions) {
  const router = useRouter();
  const client = useQueryClient();
  const [agree, setAgree] = useState(initialAgree);
  const [email, setEmail] = useState("");
  const [emailConsent, setEmailConsent] = useState(false);
  const saveEmail = useSaveContactEmail();
  // 필수 동의를 서버에 남겨요 (2026-11-16 보안 감사 L-2: 예전에는 화면 상태로만 있었어요)
  const agreeTerms = useMutation({
    mutationFn: async () => {
      if (USE_MOCKS) return;
      await api.post(endpoints.usersMeTerms, {
        termsVersion: versions.terms,
        privacyVersion: versions.privacy,
        ageOver14: agree.age,
      });
    },
    // 내 정보도 바로 동의로 바꿔요 (환영 화면으로 가는 사이 동의 화면으로 되돌려 보내지 않게)
    onSuccess: () => {
      client.setQueryData<Session | null>(sessionKey, (s) => (s ? { ...s, termsAgreed: true } : s));
      if (!USE_MOCKS) void client.invalidateQueries({ queryKey: sessionKey });
    },
  });

  const all = signupTerms.every((t) => agree[t.key]);
  const requiredOk = signupTerms.filter((t) => t.required).every((t) => agree[t.key]);
  // 이메일은 선택: 비워 두거나, 적었다면 형식이 맞고 수집·이용에 동의해야 해요
  const emailOk = email.trim() === "" || (isEmail(email) && emailConsent);
  const pending = agreeTerms.isPending || saveEmail.isPending;
  const ready = requiredOk && emailOk && !pending;

  /** 동의를 먼저 기록하고(실패하면 이 화면에 남아요), 이메일을 적었으면 저장한 뒤 가입 완료로 */
  const finish = async () => {
    if (!agreeTerms.isSuccess) {
      try {
        await agreeTerms.mutateAsync();
      } catch {
        return;
      }
    }
    if (email.trim() === "") {
      router.push(routes.welcome);
      return;
    }
    saveEmail.mutate(email, { onSuccess: () => router.push(routes.welcome) });
  };

  return {
    agree,
    all,
    ready,
    email,
    setEmail,
    emailConsent,
    setEmailConsent,
    emailError: saveEmail.isError ? contactEmailError(saveEmail.error) : undefined,
    /** 동의 기록 실패 문구 */
    termsError: agreeTerms.isError ? termsError(agreeTerms.error) : undefined,
    submit: () => {
      if (ready) void finish();
    },
    toggle: (key: TermKey) => setAgree((a) => ({ ...a, [key]: !a[key] })),
    toggleAll: () =>
      setAgree(
        Object.fromEntries(signupTerms.map((t) => [t.key, !all])) as Record<TermKey, boolean>,
      ),
    submitText: !requiredOk
      ? "필수 약관에 동의해 주세요"
      : !emailOk
        ? "이메일을 확인해 주세요"
        : pending
          ? "저장하는 중"
          : "동의하고 시작하기",
  };
}

/**
 * 동의하지 않고 나가기. 로그인한 채로는 어느 화면에서든 동의 화면으로 돌아오니 로그아웃하고 처음 화면으로 가요
 * (로그인하지 않고 이 화면을 연 사람은 그냥 처음 화면으로)
 */
export function useSignupLeave() {
  const { data: session } = useSession();
  const { logout, logoutError } = useLogout();
  const router = useRouter();
  const [leaving, setLeaving] = useState(false);
  const leave = async () => {
    if (leaving) return;
    if (session) {
      setLeaving(true);
      const ok = await logout();
      setLeaving(false);
      if (!ok) return;
    }
    router.replace(routes.main);
  };
  return {
    loggedIn: !!session,
    leaving,
    error: logoutError,
    leave: () => void leave(),
  };
}
