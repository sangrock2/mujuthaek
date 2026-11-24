"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { CheckBox } from "@/features/auth/components/parts";
import { ChevronDown } from "lucide-react";
import {
  CONTACT_EMAIL_CONSENT,
  contactEmailError,
  isEmail,
  useRemoveContactEmail,
  useSaveContactEmail,
} from "@/features/auth/contactEmail";
import { cn } from "@/shared/lib/cn";
import { routes } from "@/shared/lib/routes";

const inputCls =
  "rounded-control border-line bg-surface text-text min-h-[52px] w-full box-border border border-solid px-[14px] text-[16px]";

/** 이메일 입력 + [선택] 수집·이용 동의 (목적 · 항목 · 보유 기간 · 거부할 권리를 바로 아래에 보여 줘요) */
export function ContactEmailFields({
  email,
  onEmail,
  consent,
  onConsent,
  error,
}: {
  email: string;
  onEmail: (v: string) => void;
  consent: boolean;
  onConsent: (v: boolean) => void;
  error?: string;
}) {
  const id = useId();
  const typed = email.trim() !== "";
  const message =
    error ??
    (typed && !isEmail(email)
      ? "이메일 주소 형식이 아니에요"
      : typed && !consent
        ? "이메일을 저장하려면 수집·이용에 동의해 주세요"
        : undefined);
  return (
    <div className="flex flex-col gap-[12px]">
      <label htmlFor={`${id}-email`} className="flex flex-col gap-[8px] text-[15px] font-bold">
        <span>
          연락용 이메일 <span className="text-text-sub font-semibold">(선택)</span>
        </span>
        <input
          id={`${id}-email`}
          type="email"
          inputMode="email"
          autoComplete="email"
          maxLength={254}
          placeholder="name@example.com"
          value={email}
          onChange={(e) => onEmail(e.target.value)}
          aria-invalid={message ? true : undefined}
          aria-describedby={`${id}-help`}
          className={inputCls}
        />
      </label>
      <span id={`${id}-help`} className="text-text-sub text-[14px] leading-[1.6]">
        약관·개인정보처리방침 변경, 이용 제한, 계정 안내처럼 꼭 알려야 할 때만 보내요. 비워 두고
        나중에 내 정보에서 등록해도 돼요.
      </span>

      <button
        type="button"
        role="checkbox"
        aria-checked={consent}
        onClick={() => onConsent(!consent)}
        className="text-text flex min-h-[48px] cursor-pointer items-center gap-[12px] border-0 bg-transparent p-0 text-left"
      >
        <CheckBox checked={consent} />
        <span className="text-[15px]">
          <span className="text-text-sub font-bold">[선택]</span> {CONTACT_EMAIL_CONSENT.label}
        </span>
      </button>
      <ConsentDetails />

      {message && (
        <span role="alert" className="text-danger-link text-[14px] font-semibold">
          {message}
        </span>
      )}
    </div>
  );
}

/** 동의 내용. 중요한 항목은 굵게 */
export function ConsentDetails({
  className,
  sharedAddress = false,
}: {
  className?: string;
  sharedAddress?: boolean;
}) {
  return (
    <div
      className={cn(
        "bg-fill text-text-sub flex flex-col gap-[6px] rounded-sm px-[14px] py-[12px] text-[14px] leading-[1.6]",
        className,
      )}
    >
      <dl className="m-0 flex flex-col gap-[4px]">
        {CONTACT_EMAIL_CONSENT.rows.map((r) => (
          <div key={r.term} className="flex gap-[10px]">
            <dt className="w-[64px] flex-none">{r.term}</dt>
            <dd className="text-text m-0 font-bold">{r.desc}</dd>
          </div>
        ))}
      </dl>
      <span>
        {sharedAddress
          ? "동의하지 않아도 서비스를 이용할 수 있어요. 이 동의는 계정 안내에만 적용돼요."
          : CONTACT_EMAIL_CONSENT.refuse}
      </span>
      <Link
        href={routes.privacy}
        className="text-text hover:text-text self-start text-[14px] font-bold"
      >
        개인정보처리방침 보기
      </Link>
    </div>
  );
}

/** 공동 이메일 입력란의 주소를 계정 안내에도 쓸지 관리해요. */
export function ContactEmailPurpose({
  address,
  current,
  locked,
  onSaved,
}: {
  address: string;
  current: string | null;
  locked: boolean;
  onSaved: () => void;
}) {
  const save = useSaveContactEmail();
  const remove = useRemoveContactEmail();
  const [consentFor, setConsentFor] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const value = address.trim();
  const separator = value.lastIndexOf("@") + 1;
  const normalized = value.slice(0, separator) + value.slice(separator).toLowerCase();
  const same = current !== null && current === normalized;
  const consenting = consentFor === normalized;
  const busy = locked || save.isPending || remove.isPending;

  return (
    <details className="group border-line-soft border-t pt-[6px]">
      <summary className="text-text flex min-h-[44px] cursor-pointer list-none items-center gap-[8px] text-[14px] [&::-webkit-details-marker]:hidden">
        <span className="min-w-0 flex-1 font-bold">계정 안내에 이메일 사용</span>
        <span className="text-text-sub shrink-0 text-[13px]">{current ? "사용 중" : "선택"}</span>
        <ChevronDown
          size={16}
          aria-hidden
          className="text-text-sub shrink-0 group-open:rotate-180"
        />
      </summary>
      <div className="flex flex-col gap-[9px] pb-[7px]">
        {current && !same && (
          <p className="text-text-sub text-[13px] break-all">
            현재 계정 안내 주소 <strong>{current}</strong>
          </p>
        )}
        {!same && (
          <>
            <ConsentDetails sharedAddress />
            <label className="flex min-h-[36px] items-center gap-[8px] text-[14px]">
              <input
                type="checkbox"
                className="accent-brand size-[16px] shrink-0"
                checked={consenting}
                disabled={busy || !isEmail(value)}
                onChange={(event) => setConsentFor(event.target.checked ? normalized : null)}
              />
              {CONTACT_EMAIL_CONSENT.label}
            </label>
            {!isEmail(value) && (
              <p className="text-text-sub text-[13px]">위 입력란에 이메일 주소를 입력해 주세요.</p>
            )}
          </>
        )}
        <div className="flex flex-wrap items-center gap-[10px]">
          {!same && (
            <button
              type="button"
              className="border-line bg-surface rounded-control min-h-[44px] border px-[12px] text-[14px] font-bold disabled:opacity-50"
              disabled={busy || !consenting || !isEmail(value)}
              onClick={() => {
                setNotice("");
                remove.reset();
                save.mutate(value, {
                  onSuccess: () => {
                    setConsentFor(null);
                    setNotice("이 주소를 계정 안내에도 사용해요.");
                    onSaved();
                  },
                });
              }}
            >
              {save.isPending ? "저장하는 중" : "이 주소를 계정 안내에 사용"}
            </button>
          )}
          {current && (
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setNotice("");
                setConsentFor(null);
                save.reset();
                remove.mutate(undefined, {
                  onSuccess: () => setNotice("계정 안내 이메일 동의를 철회했어요."),
                });
              }}
              className="text-text-sub min-h-[44px] text-[14px] font-semibold underline-offset-4 hover:underline"
            >
              계정 안내 동의 철회
            </button>
          )}
        </div>
        {save.isError && (
          <p role="alert" className="text-danger-link text-[13px]">
            {contactEmailError(save.error)}
          </p>
        )}
        {remove.isError && (
          <p role="alert" className="text-danger-link text-[13px]">
            계정 안내 동의를 철회하지 못했어요. 잠시 뒤 다시 시도해 주세요.
          </p>
        )}
        {notice && (
          <p role="status" className="text-brand-strong text-[13px]">
            {notice}
          </p>
        )}
      </div>
    </details>
  );
}
