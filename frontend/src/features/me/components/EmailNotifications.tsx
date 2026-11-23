"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isMember, useSession } from "@/features/auth/session";
import { api, ApiError } from "@/shared/lib/api/client";

type Preferences = { newNotice: boolean; deadline: boolean; reportAnswer: boolean };
type Status = Preferences & { email: string | null; verified: boolean; enabled: boolean };
type Action = "request" | "save" | "edit" | "withdraw";

const path = "/api/users/me/email-notifications";
const empty: Status = {
  email: null,
  verified: false,
  enabled: false,
  newNotice: false,
  deadline: false,
  reportAnswer: false,
};
const options = [
  ["newNotice", "맞춤 신규 공고·지원 소식"],
  ["deadline", "신청 준비함·관심 공고 마감 3일 전·1일 전"],
  ["reportAnswer", "문의·제보 답변 도착"],
] as const;
const defaultPreferences = { newNotice: true, deadline: true, reportAnswer: true };
const button =
  "min-h-[44px] rounded-sm border border-line px-[14px] text-[14px] font-bold disabled:opacity-50";

function emailError(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 429) return "인증 메일은 1분 간격으로 하루 5회까지 요청할 수 있어요.";
    if (error.code === "EMAIL_ADDRESS_LOCKED")
      return "주소를 바꾸려면 이메일 수정하기를 눌러 주세요.";
    if (error.code === "EMAIL_DELIVERY_UNAVAILABLE")
      return "메일을 보내지 못했어요. 잠시 뒤 다시 요청해 주세요.";
    if (error.code === "VALIDATION_FAILED") return "올바른 이메일 주소를 입력해 주세요.";
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
    enabled: isMember(session.data),
    retry: false,
  });
  const [address, setAddress] = useState("");
  const [collectionConsent, setCollectionConsent] = useState(false);
  const [consent, setConsent] = useState(false);
  const [draft, setDraft] = useState<Preferences | null>(null);
  const [message, setMessage] = useState("");
  const data = query.data;
  const value = draft ?? (data?.enabled ? data : defaultPreferences);
  const mutation = useMutation({
    mutationFn: async (action: Action) => {
      if (action === "request")
        return api.post<Status>(path + "/request", {
          email: data?.email ?? address,
          consent: Boolean(data?.email) || collectionConsent,
        });
      if (action === "save")
        return api.put<Status>(path, {
          enabled: true,
          newNotice: value.newNotice,
          deadline: value.deadline,
          reportAnswer: value.reportAnswer,
          consent,
        });
      if (action === "edit") return api.post<Status>(path + "/edit");
      await api.delete(path);
      return empty;
    },
    onMutate: () => setMessage(""),
    onSuccess: (updated, action) => {
      client.setQueryData(key, updated);
      setDraft(null);
      setConsent(false);
      setAddress("");
      setCollectionConsent(false);
      setMessage(
        {
          request: "인증 메일을 보냈어요. 15분 안에 메일에 있는 링크를 열어 주세요.",
          edit: "이전 인증 링크가 만료됐어요. 새 주소를 입력해 주세요.",
          withdraw: "이메일 알림 동의를 철회했어요.",
          save: "이메일 알림 설정을 저장했어요.",
        }[action],
      );
    },
    onError: (error, action) => {
      setMessage(emailError(error));
      if (action === "request") void client.invalidateQueries({ queryKey: key });
    },
  });
  if (!session.data) return null;
  return (
    <section
      className="border-line flex flex-col gap-[14px] border-t pt-[24px]"
      aria-label="이메일 알림"
    >
      <h3 className="text-[18px] font-extrabold">이메일로 받기</h3>
      <p className="text-text-sub text-[14px]">
        계정 연락용 이메일과 별도로 등록해요. 주소 인증 후 수신에 동의하면 알림이 켜져요.
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
              value={data?.email ?? address}
              readOnly={Boolean(data?.email) || mutation.isPending}
              onChange={(event) => setAddress(event.target.value)}
              className="border-line bg-surface min-h-[44px] rounded-sm border px-[12px]"
            />
          </label>
          {data?.email ? (
            <>
              <p className="text-text-sub text-[14px]">
                {data.verified
                  ? data.enabled
                    ? "인증 완료 · 알림 수신 중"
                    : "인증 완료 · 수신 동의 대기"
                  : "이메일 인증 대기"}
              </p>
              {!data.verified && (
                <>
                  <p className="text-text-sub text-[13px]">
                    인증 메일을 다시 요청하면 이전 링크가 만료돼요.
                  </p>
                  <button
                    type="button"
                    className={button}
                    disabled={mutation.isPending}
                    onClick={() => mutation.mutate("request")}
                  >
                    인증 메일 다시 받기
                  </button>
                </>
              )}
              <p className="text-text-sub text-[13px]">
                이메일을 수정하면 이 주소의 인증과 수신 동의가 초기화돼요.
              </p>
              <button
                type="button"
                className={button}
                disabled={mutation.isPending}
                onClick={() => mutation.mutate("edit")}
              >
                이메일 수정하기
              </button>
            </>
          ) : (
            <>
              <p className="text-text-sub text-[13px]">
                이메일 주소는 인증과 선택한 알림에 사용해요. 동의를 철회하거나 탈퇴하면 주소를
                삭제해요. 미인증 주소는 24시간 뒤 정기 삭제해요.{" "}
                <a href="/privacy">개인정보처리방침</a>
              </p>
              <label className="flex items-center gap-[8px] text-[14px]">
                <input
                  type="checkbox"
                  checked={collectionConsent}
                  onChange={(event) => setCollectionConsent(event.target.checked)}
                />
                [선택] 알림 이메일 수집·이용에 동의해요
              </label>
              <button
                type="button"
                className={button}
                disabled={mutation.isPending || !collectionConsent || !address.trim()}
                onClick={() => mutation.mutate("request")}
              >
                동의하고 인증 메일 받기
              </button>
            </>
          )}
          {data?.verified && (
            <fieldset className="flex flex-col gap-[12px]" disabled={mutation.isPending}>
              <legend className="mb-[10px] font-bold">받을 이메일 알림</legend>
              {options.map(([name, label]) => (
                <label key={name} className="flex items-center gap-[8px]">
                  <input
                    type="checkbox"
                    checked={value[name]}
                    onChange={(event) => setDraft({ ...value, [name]: event.target.checked })}
                  />
                  {label}
                </label>
              ))}
              {!data.enabled && (
                <label className="flex items-center gap-[8px] text-[14px]">
                  <input
                    type="checkbox"
                    checked={consent}
                    onChange={(event) => setConsent(event.target.checked)}
                  />
                  [선택] 선택한 알림을 이메일로 받는 데 동의해요
                </label>
              )}
              <button
                type="button"
                className={button}
                disabled={(!data.enabled && !consent) || !options.some(([name]) => value[name])}
                onClick={() => mutation.mutate("save")}
              >
                {data.enabled ? "알림 설정 저장" : "동의하고 알림 받기"}
              </button>
            </fieldset>
          )}
          {data?.email && (
            <button
              type="button"
              className={button}
              disabled={mutation.isPending}
              onClick={() => mutation.mutate("withdraw")}
            >
              동의 철회
            </button>
          )}
        </>
      )}
      {message && (
        <p role={mutation.isError ? "alert" : "status"} className="text-[14px]">
          {message}
        </p>
      )}
    </section>
  );
}
