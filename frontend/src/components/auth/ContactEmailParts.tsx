"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { CheckBox } from "@/components/auth/parts";
import { useSession } from "@/features/auth/session";
import {
  CONTACT_EMAIL_CONSENT,
  contactEmailError,
  isEmail,
  useRemoveContactEmail,
  useSaveContactEmail,
} from "@/features/auth/contactEmail";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";

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
export function ConsentDetails({ className }: { className?: string }) {
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
      <span>{CONTACT_EMAIL_CONSENT.refuse}</span>
      <Link
        href={routes.privacy}
        className="text-text hover:text-text self-start text-[14px] font-bold"
      >
        개인정보처리방침 보기
      </Link>
    </div>
  );
}

/** 내 정보: 연락용 이메일 보기 · 등록 · 바꾸기 · 지우기 */
export function ContactEmailCard({ className }: { className?: string }) {
  const { data: session } = useSession();
  const save = useSaveContactEmail();
  const remove = useRemoveContactEmail();
  const [editing, setEditing] = useState(false);
  const [email, setEmail] = useState("");
  const [consent, setConsent] = useState(false);

  const current = session?.email ?? null;
  const canSave = isEmail(email) && consent && !save.isPending;
  const startEdit = () => {
    setEmail(current ?? "");
    setConsent(false);
    save.reset();
    setEditing(true);
  };

  return (
    <section aria-label="연락용 이메일" className={cn("flex flex-col gap-[12px]", className)}>
      <div className="flex items-center justify-between gap-[12px]">
        <span className="flex min-w-0 flex-col gap-[2px]">
          <span className="text-[16px] font-extrabold">연락용 이메일</span>
          <span className="text-text-sub truncate text-[14px]">
            {session === undefined ? "불러오는 중" : (current ?? "등록하지 않았어요 (선택)")}
          </span>
        </span>
        {!editing && session && (
          <button
            type="button"
            onClick={startEdit}
            className="bg-fill text-text min-h-[44px] flex-none cursor-pointer rounded-sm border-0 px-[14px] text-[14px] font-bold"
          >
            {current ? "바꾸기" : "등록하기"}
          </button>
        )}
      </div>

      {editing && (
        <form
          className="flex flex-col gap-[12px]"
          onSubmit={(e) => {
            e.preventDefault();
            if (canSave) save.mutate(email, { onSuccess: () => setEditing(false) });
          }}
        >
          <ContactEmailFields
            email={email}
            onEmail={setEmail}
            consent={consent}
            onConsent={setConsent}
            error={save.isError ? contactEmailError(save.error) : undefined}
          />
          <div className="flex gap-[8px]">
            <button
              type="submit"
              disabled={!canSave}
              className="bg-brand disabled:bg-line disabled:text-text-sub min-h-[48px] flex-1 cursor-pointer rounded-sm border-0 text-[15px] font-bold text-white disabled:cursor-default"
            >
              {save.isPending ? "저장하는 중" : "동의하고 저장"}
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="bg-fill text-text min-h-[48px] cursor-pointer rounded-sm border-0 px-[16px] text-[15px] font-bold"
            >
              취소
            </button>
          </div>
        </form>
      )}

      {!editing && current && (
        <button
          type="button"
          disabled={remove.isPending}
          onClick={() => remove.mutate()}
          className="text-text-sub inline-flex min-h-[44px] cursor-pointer items-center self-start border-0 bg-transparent p-0 text-[14px] font-semibold"
        >
          이메일 지우기 (동의 철회)
        </button>
      )}
      {remove.isError && (
        <span role="alert" className="text-danger-link text-[14px] font-semibold">
          지우지 못했어요. 잠시 뒤 다시 시도해 주세요
        </span>
      )}
    </section>
  );
}
