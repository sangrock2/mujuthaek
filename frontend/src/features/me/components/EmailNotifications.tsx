"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "@/features/auth/session";
import { api, ApiError } from "@/shared/lib/api/client";
import { Toggle } from "@/shared/ui/Toggle";

type Settings = { enabled: boolean; newNotice: boolean; deadline: boolean; reportAnswer: boolean };
type Status = Settings & { email: string | null; verified: boolean };
const path = "/api/users/me/email-notifications";
const labels = {
  newNotice: "맞춤 신규 공고·지원 소식",
  deadline: "신청 준비함·관심 공고 마감 3일 전·1일 전",
  reportAnswer: "문의·제보 답변 도착",
} as const;
const button =
  "min-h-[44px] rounded-sm border border-line px-[14px] text-[14px] font-bold disabled:opacity-50";

export function emailError(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 429) return "인증 메일은 1분 간격으로 하루 5회까지 요청할 수 있어요.";
    if (error.code === "EMAIL_VERIFICATION_INVALID")
      return "인증 링크가 만료됐거나 이미 사용됐어요. 다시 요청해 주세요.";
    if (error.code === "EMAIL_DELIVERY_UNAVAILABLE")
      return "메일 발송을 준비 중이거나 일시적으로 연결하지 못했어요. 잠시 뒤 다시 요청해 주세요.";
  }
  return "처리하지 못했어요. 잠시 뒤 다시 해 주세요.";
}

export function EmailNotifications() {
  const session = useSession();
  const client = useQueryClient();
  const key = ["me", "email-notifications", session.data?.id];
  const query = useQuery({
    queryKey: key,
    queryFn: () => api.get<Status>(path),
    enabled: !!session.data,
    retry: false,
  });
  const [address, setAddress] = useState<string>();
  const [collectionConsent, setCollectionConsent] = useState(false);
  const [consent, setConsent] = useState(false);
  const [draft, setDraft] = useState<Settings | null>(null);
  const [message, setMessage] = useState("");
  const mutation = useMutation({
    mutationFn: async (action: "request" | "save" | "delete") => {
      if (action === "request")
        return api.post<Status>(path + "/request", {
          email: address ?? query.data?.email ?? "",
          consent: collectionConsent,
        });
      if (action === "save") return api.put<Status>(path, { ...value, consent });
      await api.delete(path);
      return {
        email: null,
        verified: false,
        enabled: false,
        newNotice: false,
        deadline: false,
        reportAnswer: false,
      } as Status;
    },
    onSuccess: (data, action) => {
      client.setQueryData(key, data);
      setDraft(null);
      setConsent(false);
      if (action === "delete") {
        setAddress("");
        setCollectionConsent(false);
      }
      setMessage(
        action === "request"
          ? "인증 메일을 보냈어요. 15분 안에 링크를 열어 주소를 인증해 주세요."
          : action === "delete"
            ? "알림 이메일을 삭제했어요."
            : "이메일 알림 설정을 저장했어요.",
      );
    },
    onError: (error) => setMessage(emailError(error)),
  });
  const data = query.data;
  const value = draft ??
    data ?? { enabled: false, newNotice: true, deadline: true, reportAnswer: true };
  if (!session.data) return null;
  return (
    <section
      className="border-line flex flex-col gap-[14px] border-t pt-[24px]"
      aria-label="이메일 알림"
    >
      <h3 className="text-[18px] font-extrabold">이메일로 받기</h3>
      <p className="text-text-sub text-[14px]">
        계정 연락용 이메일과 별도로 등록해요. 주소 인증 후 수신에 동의해야 알림이 켜져요. 새
        공고·지원 소식은 하루 두 번 모아 보내요.
      </p>
      {query.isPending ? (
        <p>설정을 불러오는 중이에요.</p>
      ) : query.isError ? (
        <p role="alert">
          이메일 설정을 불러오지 못했어요.{" "}
          <button type="button" onClick={() => void query.refetch()}>
            다시 불러오기
          </button>
        </p>
      ) : (
        <>
          <label className="flex flex-col gap-[6px] text-[14px]">
            알림 받을 이메일
            <input
              type="email"
              autoComplete="email"
              maxLength={254}
              value={address ?? data?.email ?? ""}
              onChange={(e) => setAddress(e.target.value)}
              className="border-line bg-surface min-h-[44px] rounded-sm border px-[12px]"
            />
          </label>
          <p className="text-text-sub text-[13px]">
            이메일 주소는 인증과 선택한 알림 발송에 사용하며, 탈퇴 또는 알림 이메일 삭제 시
            삭제해요. 미인증 주소는 24시간 경과 후 정기 삭제해요. 동의하지 않아도 다른 서비스는
            이용할 수 있어요. 자세한 내용은 <a href="/privacy">개인정보처리방침</a>에서 확인해
            주세요.
          </p>
          <label className="flex items-center gap-[8px] text-[14px]">
            <input
              type="checkbox"
              checked={collectionConsent}
              onChange={(e) => setCollectionConsent(e.target.checked)}
            />
            [선택] 알림 이메일 수집·이용에 동의해요
          </label>
          <button
            type="button"
            className={button}
            disabled={mutation.isPending || !collectionConsent || !(address ?? data?.email)}
            onClick={() => mutation.mutate("request")}
          >
            동의하고 인증 메일 받기
          </button>
          {data?.email && (
            <p className="text-[14px]">
              현재 주소: {data.email} · {data.verified ? "인증 완료" : "인증 대기"} ·{" "}
              {data.enabled ? "수신 중" : "수신 꺼짐"}
            </p>
          )}
          {data?.verified && (
            <fieldset className="flex flex-col gap-[12px]" disabled={mutation.isPending}>
              <legend className="mb-[10px] font-bold">받을 이메일 알림</legend>
              {Object.entries(labels).map(([name, label]) => (
                <label key={name} className="flex items-center gap-[8px]">
                  <input
                    type="checkbox"
                    checked={value[name as keyof typeof labels]}
                    onChange={(e) => setDraft({ ...value, [name]: e.target.checked })}
                  />
                  {label}
                </label>
              ))}
              <div className="flex items-center justify-between gap-[12px]">
                <span>이메일 알림 수신</span>
                <Toggle
                  checked={value.enabled}
                  onChange={(enabled) => setDraft({ ...value, enabled })}
                  label="이메일 알림 수신"
                />
              </div>
              {value.enabled && (
                <label className="flex items-center gap-[8px] text-[14px]">
                  <input
                    type="checkbox"
                    checked={consent}
                    onChange={(e) => setConsent(e.target.checked)}
                  />
                  [선택] 선택한 공고·마감·답변 알림을 이메일로 받는 데 동의해요. 언제든 해제할 수
                  있어요.
                </label>
              )}
              <button
                type="button"
                className={button}
                disabled={value.enabled && !consent}
                onClick={() => mutation.mutate("save")}
              >
                알림 설정 저장
              </button>
            </fieldset>
          )}
          {data?.email && (
            <button
              type="button"
              className={button}
              disabled={mutation.isPending}
              onClick={() => mutation.mutate("delete")}
            >
              알림 이메일 삭제·수신 중단
            </button>
          )}
        </>
      )}
      {message && (
        <p role="status" className="text-[14px]">
          {message}
        </p>
      )}
    </section>
  );
}
