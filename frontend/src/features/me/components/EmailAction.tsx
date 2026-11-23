"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { API_BASE_URL } from "@/shared/lib/api/client";

export function EmailAction({ action }: { action: "verify" | "unsubscribe" }) {
  const client = useQueryClient();
  const verify = action === "verify";
  const initialAction = useRef<string>(null);
  const [token, setToken] = useState("");
  const [status, setStatus] = useState<"loading" | "ready" | "busy" | "done" | "invalid" | "retry">(
    "loading",
  );

  const submit = useCallback(
    async (linkToken: string) => {
      setStatus("busy");
      try {
        const response = await fetch(`${API_BASE_URL}/api/email-notifications/${action}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "omit",
          cache: "no-store",
          referrerPolicy: "no-referrer",
          body: JSON.stringify({ token: linkToken }),
        });
        if (response.ok) {
          setStatus("done");
          setToken("");
          void client.invalidateQueries({ queryKey: ["me", "email-notifications"] });
        } else if (response.status === 400) {
          setStatus("invalid");
          setToken("");
        } else {
          setStatus("retry");
        }
      } catch {
        setStatus("retry");
      }
    },
    [action, client],
  );

  useEffect(() => {
    if (initialAction.current === action) return;
    initialAction.current = action;
    const linkToken = new URLSearchParams(window.location.hash.slice(1)).get("token");
    window.history.replaceState(
      window.history.state,
      "",
      window.location.pathname + window.location.search,
    );
    queueMicrotask(() => {
      if (!linkToken) {
        setStatus("invalid");
        return;
      }
      setToken(linkToken);
      if (verify) void submit(linkToken);
      else setStatus("ready");
    });
  }, [action, submit, verify]);

  return (
    <main className="mx-auto flex max-w-[560px] flex-col gap-[20px] px-[24px] py-[60px]">
      <h1 className="text-[24px] font-extrabold">
        {verify ? "알림 이메일 인증" : "이메일 알림 동의 철회"}
      </h1>
      {(status === "busy" || status === "loading") && <p role="status">처리 중이에요.</p>}
      {status === "done" && (
        <p role="status">
          {verify
            ? "이메일 주소를 인증했어요. 알림 설정에서 받을 종류를 선택하고 수신에 동의해 주세요."
            : "이메일 알림 동의를 철회했어요."}
        </p>
      )}
      {status === "invalid" && (
        <p role="alert">
          {verify
            ? "인증 링크가 만료됐거나 이미 사용됐어요. 알림 설정에서 새 인증 메일을 요청해 주세요."
            : "이 링크로 동의를 철회할 수 없어요. 알림 설정에서 확인해 주세요."}
        </p>
      )}
      {status === "retry" && <p role="alert">일시적으로 처리하지 못했어요. 다시 시도해 주세요.</p>}
      {status === "ready" && <p>이 계정에서 등록한 알림 이메일과 수신 동의를 철회해요.</p>}
      {(status === "ready" || status === "retry") && (
        <button
          type="button"
          onClick={() => void submit(token)}
          className="bg-brand min-h-[48px] rounded-sm px-[18px] font-bold text-white"
        >
          {status === "retry" ? "다시 시도하기" : "동의 철회"}
        </button>
      )}
      <Link href="/me/notifications">알림 설정으로 이동</Link>
    </main>
  );
}
