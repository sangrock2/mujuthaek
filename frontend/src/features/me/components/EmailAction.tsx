"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { useSession } from "@/features/auth/session";
import { api } from "@/shared/lib/api/client";
import { emailError } from "./EmailNotifications";

export function EmailAction({ action }: { action: "verify" | "unsubscribe" }) {
  const session = useSession();
  const client = useQueryClient();
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const loaded = useRef(false);
  useEffect(() => {
    if (loaded.current) return;
    loaded.current = true;
    setToken(new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "");
    window.history.replaceState(null, "", window.location.pathname);
  }, []);
  async function submit() {
    setBusy(true);
    setError("");
    try {
      const path =
        action === "verify"
          ? "/api/users/me/email-notifications/verify"
          : "/api/email-notifications/unsubscribe";
      await api.post(path, { token });
      setDone(true);
      setToken("");
      await client.invalidateQueries({ queryKey: ["me", "email-notifications"] });
    } catch (failure) {
      setError(emailError(failure));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="mx-auto flex max-w-[560px] flex-col gap-[20px] px-[24px] py-[60px]">
      <h1 className="text-[24px] font-extrabold">
        {action === "verify" ? "알림 이메일 인증" : "이메일 수신 해제"}
      </h1>
      {done ? (
        <p role="status">
          {action === "verify"
            ? "주소를 인증했어요. 알림 설정에서 받을 종류를 선택하고 수신에 동의하면 알림이 켜져요."
            : "이메일 알림 수신을 중단했어요."}
        </p>
      ) : (
        <>
          <p>
            {action === "verify"
              ? "인증 메일을 요청한 계정으로 로그인한 뒤 아래 버튼을 눌러 주세요."
              : "아래 버튼을 누르면 이 주소로 보내는 공고·마감·답변 이메일 알림을 모두 중단해요."}
          </p>
          {action === "verify" && !session.data ? (
            <p>
              <Link href="/login">로그인하기</Link> · 로그인 후 메일의 인증 링크를 다시 열어 주세요.
            </p>
          ) : (
            <button
              type="button"
              disabled={!token || busy}
              onClick={() => void submit()}
              className="bg-brand min-h-[48px] rounded-sm px-[18px] font-bold text-white disabled:opacity-50"
            >
              {busy
                ? "처리 중…"
                : action === "verify"
                  ? "이메일 주소 인증하기"
                  : "이메일 수신 해제하기"}
            </button>
          )}
          {!token && <p>메일에서 링크를 다시 열어 주세요.</p>}
        </>
      )}
      {error && <p role="alert">{error}</p>}
      <Link href="/me?tab=notifications">알림 설정으로 이동</Link>
    </main>
  );
}
