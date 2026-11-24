"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ContactEmailPurpose } from "@/features/auth/components/ContactEmailParts";
import { isMember, useSession } from "@/features/auth/session";
import { api, ApiError } from "@/shared/lib/api/client";
import { cn } from "@/shared/lib/cn";
import { meTabHref } from "./MeNavigation";

type Preferences = { newNotice: boolean; deadline: boolean; reportAnswer: boolean };
type Verification = {
  expiresAt: string;
  resendAt: string;
  serverTime: string;
  attemptsRemaining: number;
};
type Status = Preferences & {
  email: string | null;
  verified: boolean;
  enabled: boolean;
  verification?: Verification | null;
};
type Action = "request" | "verify" | "save" | "edit" | "withdraw";

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
const initialPreferences = { newNotice: true, deadline: true, reportAnswer: true };
const button =
  "inline-flex min-h-[44px] shrink-0 items-center justify-center rounded-sm px-[12px] text-[14px] font-bold disabled:opacity-50";
const primary = cn(button, "bg-brand text-white");
const secondary = cn(button, "border-line bg-surface border");
const input =
  "border-line bg-surface text-text min-h-[44px] min-w-0 rounded-sm border px-[12px] text-[15px]";

function emailError(error: unknown, action: Action) {
  if (error instanceof ApiError) {
    if (error.status === 429) return "인증번호는 1분 간격으로 하루 5회까지 요청할 수 있어요.";
    if (error.code === "EMAIL_CODE_EXPIRED") return "인증번호가 만료됐어요. 다시 받아 주세요.";
    if (error.code === "EMAIL_CODE_EXHAUSTED")
      return "확인 횟수를 모두 사용했어요. 인증번호를 다시 받아 주세요.";
    if (error.code === "EMAIL_CODE_INVALID" && action === "verify")
      return "인증번호가 일치하지 않아요. 메일을 확인해 주세요.";
    if (error.code === "EMAIL_ADDRESS_LOCKED") return "주소를 바꾸려면 수정하기를 눌러 주세요.";
    if (error.code === "EMAIL_DELIVERY_UNAVAILABLE")
      return "메일을 보내지 못했어요. 잠시 뒤 다시 요청해 주세요.";
    if (error.code === "VALIDATION_FAILED" && action === "request")
      return "올바른 이메일 주소를 입력해 주세요.";
  }
  return "처리하지 못했어요. 잠시 뒤 다시 해 주세요.";
}

function remainingSeconds(until: string, verification: Verification, elapsed: number) {
  return Math.max(
    0,
    Math.ceil((Date.parse(until) - Date.parse(verification.serverTime) - elapsed) / 1000),
  );
}

function clockLabel(seconds: number) {
  return [Math.floor(seconds / 60), seconds % 60]
    .map((part) => String(part).padStart(2, "0"))
    .join(":");
}

export function useEmailNotificationStatus() {
  const { data: session } = useSession();
  const member = isMember(session);
  const key = ["me", "email-notifications", session?.id] as const;
  const query = useQuery({
    queryKey: key,
    queryFn: () => api.get<Status>(path),
    enabled: member,
    retry: false,
  });
  return { member, key, query, contactEmail: session?.email ?? null };
}

export function EmailNotificationChannel() {
  const { member, query } = useEmailNotificationStatus();
  if (!member) return null;
  const data = query.data;
  const active = !!(data?.verified && data.enabled);
  const status = query.isPending
    ? "확인 중"
    : query.isError
      ? "상태 확인 실패"
      : active
        ? "수신 중"
        : data?.verified
          ? "수신 설정 필요"
          : data?.email
            ? "인증 대기"
            : "미등록";

  return (
    <div className="border-line-soft flex flex-wrap items-center justify-between gap-x-[12px] gap-y-[2px] border-t pt-[8px]">
      <span className="flex min-h-[44px] items-center gap-[8px] text-[14px] font-bold">
        이메일 알림
        <span
          role="status"
          className={cn(
            "rounded-badge px-[8px] py-[4px] text-[12px] font-semibold",
            active ? "bg-brand-soft text-brand-strong" : "bg-fill text-text-sub",
          )}
        >
          {status}
        </span>
      </span>
      <Link
        href={meTabHref("privacy", true)}
        className="text-brand-strong inline-flex min-h-[44px] items-center text-[14px] font-bold underline-offset-4"
      >
        개인정보 설정에서 관리
      </Link>
    </div>
  );
}

export function EmailNotifications() {
  const client = useQueryClient();
  const { member, key, query, contactEmail } = useEmailNotificationStatus();
  const [draftAddress, setDraftAddress] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [draft, setDraft] = useState<Preferences | null>(null);
  const [message, setMessage] = useState("");
  const [now, setNow] = useState(0);
  const dialog = useRef<HTMLDialogElement>(null);
  const addressField = useRef<HTMLInputElement>(null);
  const addressId = useId();
  const codeId = useId();
  const withdrawalTitleId = useId();
  const data = query.data;
  const address = data?.email ?? draftAddress ?? contactEmail ?? "";
  const verification = data?.verification;
  const elapsed = Math.max(0, now - query.dataUpdatedAt);
  const seconds = verification
    ? remainingSeconds(verification.expiresAt, verification, elapsed)
    : 0;
  const resend = verification ? remainingSeconds(verification.resendAt, verification, elapsed) : 0;
  const ticking = seconds > 0 || resend > 0;
  const canVerify = seconds > 0 && !!verification?.attemptsRemaining;
  const preferences = draft ?? (data?.enabled ? data : initialPreferences);

  useEffect(() => {
    if (!ticking) return;
    const tick = () => setNow(Date.now());
    const interval = window.setInterval(tick, 250);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [ticking]);

  const mutation = useMutation({
    mutationFn: async (action: Action) => {
      if (action === "request")
        return api.post<Status>(path + "/request-code", {
          email: data?.email ?? address.trim(),
          consent: true,
        });
      if (action === "verify") return api.post<Status>(path + "/verify-code", { code });
      if (action === "save")
        return api.put<Status>(path, {
          enabled: true,
          newNotice: preferences.newNotice,
          deadline: preferences.deadline,
          reportAnswer: preferences.reportAnswer,
          consent: !data?.enabled,
        });
      if (action === "edit") return api.post<Status>(path + "/edit");
      await api.delete(path);
      return empty;
    },
    onMutate: () => setMessage(""),
    onSuccess: (updated, action) => {
      client.setQueryData(key, updated);
      setDraft(null);
      setDraftAddress(action === "edit" ? "" : null);
      setCode("");
      if (action === "edit") addressField.current?.focus();
      if (action === "withdraw") dialog.current?.close();
      setMessage(
        {
          request: "인증번호를 보냈어요.",
          verify: "이메일을 인증했어요. 이제 설정한 이메일 알림을 받아요.",
          edit: "새 이메일 주소를 입력해 주세요.",
          withdraw: "이메일 알림 동의를 철회했어요.",
          save: "이메일 알림 설정을 저장했어요.",
        }[action],
      );
    },
    onError: (error, action) => {
      if (action === "withdraw") dialog.current?.close();
      setMessage(emailError(error, action));
      if (action === "request" || action === "verify")
        void client.invalidateQueries({ queryKey: key });
    },
  });
  const busy = mutation.isPending;
  const hasPreference = options.some(([name]) => preferences[name]);

  function submitAddress(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!busy && !data?.email && address.trim()) mutation.mutate("request");
  }

  function submitCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!busy && canVerify && code.length === 6) mutation.mutate("verify");
  }

  if (!member) return null;
  return (
    <section
      className="border-line-soft bg-surface rounded-card flex flex-col gap-[14px] border p-[17px] sm:p-[22px]"
      aria-label="이메일"
    >
      <div className="flex flex-wrap items-center justify-between gap-[8px]">
        <h2 className="text-[18px] font-extrabold">이메일</h2>
        {data?.email && (
          <span
            className={cn(
              "rounded-badge px-[8px] py-[4px] text-[12px] font-semibold",
              data.verified ? "bg-brand-soft text-brand-strong" : "bg-fill text-text-sub",
            )}
          >
            {data.verified ? "인증 완료" : "인증 대기"}
          </span>
        )}
      </div>

      {query.isPending ? (
        <p role="status">설정을 불러오는 중이에요.</p>
      ) : query.isError ? (
        <p role="alert">
          이메일 설정을 불러오지 못했어요.{" "}
          <button type="button" className="underline" onClick={() => void query.refetch()}>
            다시 불러오기
          </button>
        </p>
      ) : (
        <>
          <form className="flex flex-col gap-[8px]" onSubmit={submitAddress}>
            <label htmlFor={addressId} className="text-[14px] font-bold">
              이메일 주소
            </label>
            <div className="flex items-center gap-[8px]">
              <input
                ref={addressField}
                id={addressId}
                type="email"
                autoComplete="email"
                maxLength={254}
                required
                value={address}
                readOnly={!!data?.email || busy}
                onChange={(event) => setDraftAddress(event.target.value)}
                className={cn(
                  input,
                  "flex-1",
                  data?.email && "bg-text/10 cursor-default border-transparent",
                )}
              />
              {data?.email && (
                <button
                  type="button"
                  className={secondary}
                  disabled={busy}
                  aria-label="이메일 수정하기"
                  onClick={() => mutation.mutate("edit")}
                >
                  수정하기
                </button>
              )}
            </div>
            {!data?.email && (
              <>
                <p className="text-text-sub text-[13px]">
                  이메일 알림을 받으려면 주소를 인증해 주세요. 인증번호를 요청하면 알림 이메일의
                  수집·이용과 맞춤 공고·마감·문의 답변 알림 수신에 동의해요. 인증 후 알림을 받을 수
                  있고, 언제든 동의를 철회할 수 있어요.{" "}
                  <a className="underline" href="/privacy">
                    개인정보처리방침
                  </a>
                </p>
                <button
                  type="submit"
                  className={cn(primary, "self-start")}
                  disabled={busy || !address.trim()}
                >
                  동의하고 인증번호 받기
                </button>
              </>
            )}
          </form>

          {data?.email && !data.verified && (
            <form
              className="border-line-soft flex flex-col gap-[8px] border-t pt-[14px]"
              onSubmit={submitCode}
            >
              {verification && (
                <>
                  <label htmlFor={codeId} className="text-[14px] font-bold">
                    인증번호 6자리
                  </label>
                  <div className="flex items-center gap-[8px]">
                    <div className="relative min-w-0 flex-1">
                      <input
                        id={codeId}
                        type="text"
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        pattern="[0-9]{6}"
                        maxLength={6}
                        value={code}
                        onChange={(event) =>
                          setCode(event.target.value.replace(/[^0-9]/g, "").slice(0, 6))
                        }
                        className={cn(input, "w-full pr-[58px] tracking-[0.12em] tabular-nums")}
                        disabled={busy || !canVerify}
                        required
                      />
                      <span
                        role="timer"
                        aria-label="인증번호 남은 시간"
                        className="text-text-sub pointer-events-none absolute inset-y-0 right-[12px] flex items-center text-[13px] font-bold tabular-nums"
                      >
                        {clockLabel(seconds)}
                      </span>
                    </div>
                    <button
                      type="submit"
                      className={primary}
                      disabled={busy || !canVerify || code.length !== 6}
                    >
                      인증하기
                    </button>
                  </div>
                </>
              )}
              {!verification && (
                <p className="text-text-sub text-[13px]">
                  인증번호를 받으면 알림 이메일의 수집·이용과 맞춤 공고·마감·문의 답변 알림 수신에
                  동의해요.
                </p>
              )}
              <div className="flex flex-wrap items-center justify-between gap-x-[8px]">
                {verification && !canVerify && (
                  <p className="text-text-sub text-[13px]">
                    {seconds === 0 ? "인증번호가 만료됐어요." : "확인 횟수를 모두 사용했어요."}
                  </p>
                )}
                <button
                  type="button"
                  className={cn(button, "text-brand-strong ml-auto")}
                  disabled={busy || resend > 0}
                  onClick={() => mutation.mutate("request")}
                >
                  {verification ? "인증번호 다시 받기" : "동의하고 인증번호 받기"}
                  {resend > 0 && (
                    <span className="ml-[6px] tabular-nums">{clockLabel(resend)}</span>
                  )}
                </button>
              </div>
            </form>
          )}

          {data?.verified && (
            <fieldset
              className="border-line-soft flex flex-col gap-[8px] border-t pt-[12px]"
              disabled={busy}
            >
              <legend className="pr-[8px] text-[14px] font-bold">받을 이메일 알림</legend>
              {options.map(([name, label]) => (
                <label key={name} className="flex min-h-[30px] items-center gap-[8px] text-[14px]">
                  <input
                    type="checkbox"
                    className="accent-brand size-[16px] shrink-0"
                    checked={preferences[name]}
                    onChange={(event) => setDraft({ ...preferences, [name]: event.target.checked })}
                  />
                  {label}
                </label>
              ))}
            </fieldset>
          )}

          {data?.email && (
            <div className="border-line-soft flex flex-wrap items-center justify-between gap-[8px] border-t pt-[10px]">
              <button
                type="button"
                className={cn(button, "text-text-sub underline-offset-4 hover:underline")}
                disabled={busy}
                onClick={() => dialog.current?.showModal()}
              >
                동의 철회
              </button>
              {data.verified && (
                <button
                  type="button"
                  className={primary}
                  disabled={busy || !hasPreference}
                  onClick={() => mutation.mutate("save")}
                >
                  {data.enabled ? "알림 설정 저장" : "동의하고 알림 받기"}
                </button>
              )}
            </div>
          )}
        </>
      )}
      <ContactEmailPurpose
        address={address}
        current={contactEmail}
        locked={busy || query.isPending || query.isError}
        onSaved={() => setDraftAddress(null)}
      />
      {message && (
        <p
          role={mutation.isError ? "alert" : "status"}
          className={cn("text-[14px]", mutation.isError && "text-danger-text")}
        >
          {message}
        </p>
      )}

      <dialog
        ref={dialog}
        aria-labelledby={withdrawalTitleId}
        className="bg-surface text-text rounded-card border-line backdrop:bg-text/40 fixed inset-0 m-auto w-[calc(100%_-_32px)] max-w-[400px] border p-[20px]"
        onCancel={(event) => {
          if (busy) event.preventDefault();
        }}
      >
        <h3 id={withdrawalTitleId} className="text-[18px] font-extrabold">
          이메일 알림 동의를 철회할까요?
        </h3>
        <p className="text-text-sub my-[12px] text-[14px]">
          이메일 알림 동의가 철회되고 알림 발송이 중단돼요.
        </p>
        <div className="flex flex-wrap justify-end gap-[8px]">
          <button
            type="button"
            className={secondary}
            disabled={busy}
            onClick={() => dialog.current?.close()}
          >
            유지하기
          </button>
          <button
            type="button"
            className={cn(button, "text-danger-text border-line border")}
            disabled={busy}
            onClick={() => mutation.mutate("withdraw")}
          >
            동의 철회하기
          </button>
        </div>
      </dialog>
    </section>
  );
}
