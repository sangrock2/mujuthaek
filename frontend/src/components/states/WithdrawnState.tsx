"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { sessionKey } from "@/features/auth/session";
import { authToken } from "@/lib/api/client";
import { routes } from "@/lib/routes";

/** 탈퇴를 마친 사람이 이 기기에 남은 로그인 정보(토큰·내 정보 캐시)를 비워요 */
function useForgetAccount() {
  const client = useQueryClient();
  useEffect(() => {
    authToken.set(null);
    client.clear();
    client.setQueryData(sessionKey, null);
  }, [client]);
}

const text =
  "그동안 무주택자들을 써 주셔서 고마워요. 계정과 관심 공고 · 알림 · 제보를 모두 지웠어요.";
const note = "이 기기에 저장한 조건은 그대로 있어요. 로그인 없이도 공고를 찾아볼 수 있어요.";

/** 회원 탈퇴 완료 (PC). 백엔드가 탈퇴를 마치고 /withdrawn으로 보내요 */
export function WebWithdrawnState() {
  useForgetAccount();
  return (
    <div className="rounded-card-lg bg-surface flex flex-col items-center gap-[16px] px-[32px] py-[56px] text-center">
      <h1 className="tracking-h1 m-0 text-[26px] font-extrabold">탈퇴했어요</h1>
      <span className="text-text-sub max-w-[520px] text-[16px] leading-[1.6]">
        {text}
        <br />
        {note}
      </span>
      <div className="flex flex-wrap justify-center gap-[8px]">
        <Link
          href={routes.main}
          className="rounded-control bg-brand inline-flex min-h-[52px] items-center px-[22px] text-[16px] font-extrabold text-white no-underline hover:text-white"
        >
          처음 화면으로
        </Link>
        <Link
          href={routes.homes}
          className="rounded-control bg-fill text-text hover:text-text inline-flex min-h-[52px] items-center px-[20px] text-[16px] font-bold no-underline"
        >
          공고 찾아보기
        </Link>
      </div>
    </div>
  );
}

/** 회원 탈퇴 완료 (모바일) */
export function MWithdrawnState() {
  useForgetAccount();
  return (
    <section className="rounded-card bg-surface flex flex-col items-center gap-[12px] px-[20px] py-[28px] text-center">
      <h1 className="m-0 text-[22px] font-extrabold">탈퇴했어요</h1>
      <span className="text-text-sub text-[15px] leading-[1.6]">
        {text} {note}
      </span>
      <div className="grid grid-cols-2 gap-[8px] self-stretch">
        <Link
          href={routes.main}
          className="rounded-control bg-brand flex min-h-[52px] items-center justify-center text-[15px] font-extrabold text-white no-underline hover:text-white"
        >
          처음 화면으로
        </Link>
        <Link
          href={routes.homes}
          className="rounded-control bg-fill text-text hover:text-text flex min-h-[52px] items-center justify-center text-[15px] font-bold no-underline"
        >
          공고 찾아보기
        </Link>
      </div>
    </section>
  );
}
