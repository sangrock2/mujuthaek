"use client";

import { useId, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { sessionKey, type Session } from "@/features/auth/session";
import { api, ApiError } from "@/shared/lib/api/client";
import { USE_MOCKS } from "@/shared/lib/api/config";
import { endpoints } from "@/shared/lib/api/endpoints";

const INVALID = /[\p{Cc}\p{Cs}\p{Zl}\p{Zp}\p{Bidi_Control}]/u;
const hint = "2~24자로 입력해 주세요. 새 공고 채팅에 이 닉네임이 표시돼요.";
const button =
  "border-line bg-surface rounded-control min-h-[44px] shrink-0 border px-[12px] text-[14px] font-bold disabled:opacity-50";

export function NicknameSetting({ member }: { member: Session }) {
  const client = useQueryClient();
  const id = useId();
  const [draft, setDraft] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const value = draft?.trim() ?? "";
  const length = [...value].length;
  const valid = length >= 2 && length <= 24 && !INVALID.test(value);
  const mutation = useMutation({
    mutationFn: (nickname: string) =>
      USE_MOCKS
        ? Promise.resolve({ nickname })
        : api.put<{ nickname: string }>(endpoints.usersMeNickname, { nickname }),
    onSuccess: async ({ nickname }) => {
      await client.cancelQueries({ queryKey: sessionKey, exact: true });
      client.setQueryData<Session | null>(sessionKey, (current) =>
        current?.id === member.id ? { ...current, nickname } : current,
      );
      setDraft(null);
      setSaved(true);
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (valid && value !== member.nickname && !mutation.isPending) mutation.mutate(value);
  }

  return (
    <div className="border-line-soft flex flex-col gap-[8px] border-b pb-[9px]">
      <div className="flex min-h-[44px] items-center gap-[10px]">
        <span className="text-text-sub shrink-0 text-[14px]">닉네임</span>
        <span className="min-w-0 flex-1 text-[15px] font-bold break-words">{member.nickname}</span>
        {draft === null && (
          <button
            type="button"
            className={button}
            onClick={() => {
              setSaved(false);
              mutation.reset();
              setDraft(member.nickname);
            }}
          >
            닉네임 변경
          </button>
        )}
      </div>
      {draft !== null && (
        <form className="flex flex-col gap-[7px]" onSubmit={submit}>
          <label htmlFor={id} className="text-[14px] font-bold">
            새 닉네임
          </label>
          <input
            id={id}
            type="text"
            autoComplete="nickname"
            aria-describedby={`${id}-hint`}
            aria-invalid={length > 24 || INVALID.test(value)}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            readOnly={mutation.isPending}
            className="border-line bg-surface rounded-control min-h-[44px] min-w-0 border px-[12px] text-[15px]"
          />
          <p id={`${id}-hint`} className="text-text-sub text-[13px]">
            {hint} ({length}/24)
          </p>
          <div className="flex flex-wrap gap-[7px]">
            <button
              className="bg-brand rounded-control min-h-[44px] px-[14px] text-[14px] font-bold text-white disabled:opacity-50"
              type="submit"
              disabled={!valid || value === member.nickname || mutation.isPending}
            >
              {mutation.isPending ? "저장하는 중" : "저장"}
            </button>
            <button
              type="button"
              className={button}
              disabled={mutation.isPending}
              onClick={() => setDraft(null)}
            >
              취소
            </button>
          </div>
          {mutation.isError && (
            <p role="alert" className="text-danger-text text-[13px]">
              {mutation.error instanceof ApiError && mutation.error.status === 400
                ? "닉네임에 사용할 수 없는 문자가 있어요. 입력한 내용을 확인해 주세요."
                : "닉네임을 저장하지 못했어요. 잠시 뒤 다시 시도해 주세요."}
            </p>
          )}
        </form>
      )}
      {saved && (
        <p role="status" className="text-brand-strong text-[13px] font-semibold">
          닉네임을 변경했어요.
        </p>
      )}
    </div>
  );
}
