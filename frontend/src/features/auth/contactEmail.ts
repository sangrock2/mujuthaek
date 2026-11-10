"use client";

// 계정 연락용 이메일 (선택): 가입 마무리 화면과 내 정보에서 등록·변경·삭제해요.
// 약관·개인정보처리방침 변경, 이용 제한, 계정 안내처럼 꼭 알려야 할 때만 쓰고 광고·공고 알림은 보내지 않아요
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api/client";
import { USE_MOCKS } from "@/lib/api/config";
import { endpoints } from "@/lib/api/endpoints";
import { sessionKey, type Session } from "@/features/auth/session";

/** 동의 문구 버전. 아래 CONTACT_EMAIL_CONSENT 문구를 바꾸면 올려요 (백엔드에 동의 기록으로 남아요) */
export const CONTACT_EMAIL_CONSENT_VERSION = "email-v1";

/** [선택] 이메일 수집·이용 동의에 보여 줄 내용 (목적 · 항목 · 보유 기간 · 거부할 권리와 불이익) */
export const CONTACT_EMAIL_CONSENT = {
  label: "연락용 이메일 수집·이용 동의",
  rows: [
    { term: "수집 항목", desc: "이메일 주소" },
    {
      term: "이용 목적",
      desc: "약관·개인정보처리방침 변경, 이용 제한, 계정 관련 안내",
    },
    { term: "보유 기간", desc: "회원 탈퇴 또는 이메일 삭제 시 바로 삭제" },
  ],
  refuse:
    "동의하지 않아도 가입하고 모든 기능을 쓸 수 있어요. 대신 중요한 안내는 서비스 공지로만 받아요. 광고나 공고 알림은 이메일로 보내지 않아요.",
} as const;

export { isEmail } from "@/features/auth/emailFormat";

function setEmail(client: ReturnType<typeof useQueryClient>, email: string | null) {
  client.setQueryData<Session | null>(sessionKey, (s) => (s ? { ...s, email } : s));
}

/** 등록·변경. 성공하면 로그인 상태(GET /api/users/me)의 email도 바꿔요 */
export function useSaveContactEmail() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (email: string) => {
      const value = email.trim();
      if (!USE_MOCKS) {
        await api.put(endpoints.usersMeEmail, {
          email: value,
          consentVersion: CONTACT_EMAIL_CONSENT_VERSION,
        });
      }
      return value;
    },
    onSuccess: (email) => {
      setEmail(client, email);
      if (!USE_MOCKS) void client.invalidateQueries({ queryKey: sessionKey });
    },
  });
}

/** 삭제 (동의 철회) */
export function useRemoveContactEmail() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      if (!USE_MOCKS) await api.delete(endpoints.usersMeEmail);
    },
    onSuccess: () => setEmail(client, null),
  });
}

/** 저장 실패 문구 */
export function contactEmailError(error: unknown) {
  if (error instanceof ApiError && error.code === "EMAIL_ALREADY_USED") {
    return "이미 다른 계정에서 쓰고 있는 이메일이에요";
  }
  if (error instanceof ApiError && error.code === "VALIDATION_FAILED") {
    return "이메일 주소를 다시 확인해 주세요";
  }
  if (error instanceof ApiError && error.status === 401) {
    return "로그인이 끝났어요. 다시 로그인한 뒤 저장해 주세요";
  }
  return "저장하지 못했어요. 잠시 뒤 다시 시도해 주세요";
}
