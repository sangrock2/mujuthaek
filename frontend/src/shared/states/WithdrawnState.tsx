"use client";

import { useEffect, useSyncExternalStore } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { consumeWithdrawalMark, forgetDeviceData } from "@/features/auth/deviceData";
import { sessionKey } from "@/features/auth/session";
import { announceSessionEnded, authToken } from "@/shared/lib/api/client";
import { routes } from "@/shared/lib/routes";

/**
 * 이 탭에서 방금 탈퇴를 시작했는지. 표시는 한 번 읽으면 지워지니 이 페이지를 연 동안 결과를 기억해요
 * (PC·모바일 화면이 바뀌어 다시 그리거나 개발 모드에서 두 번 불려도 같은 답이에요)
 */
let startedHere: boolean | undefined;
const withdrawalStartedHere = () => (startedHere ??= consumeWithdrawalMark());
const noSubscription = () => () => {};

/**
 * 탈퇴를 마친 사람이 이 기기에 남은 로그인 정보(토큰·내 정보 캐시)를 비워요.
 * 이 탭에서 탈퇴를 시작했으면 이 기기에 저장한 조건·사업 정보·최근 검색어도 지우고 다른 탭에도 알려요
 * (2026-11-16 보안 감사 L-3). 로그인 없이 열리는 화면이라 링크만으로는 기기 데이터를 지우지 않아요.
 * 돌려주는 값: 이 탭에서 시작한 탈퇴인지 (서버 렌더와 첫 화면은 null)
 */
function useForgetAccount(): boolean | null {
  const client = useQueryClient();
  const confirmed = useSyncExternalStore(noSubscription, withdrawalStartedHere, () => null);
  useEffect(() => {
    if (confirmed === null) return;
    authToken.set(null);
    if (confirmed) {
      forgetDeviceData();
      announceSessionEnded();
    }
    // clear()로 query를 제거하기 전에 기존 화면의 observer에도 로그아웃을 알려요.
    client.setQueryData(sessionKey, null);
    client.clear();
    client.setQueryData(sessionKey, null);
  }, [client, confirmed]);
  return confirmed;
}

/**
 * 「모두 지웠어요」는 이 탭에서 탈퇴를 시작했을 때만 말해요. 로그인 없이 누구나 열 수 있는 주소라,
 * 링크만 받은 사람에게 탈퇴가 끝났다고 보이면 안 돼요 (내용 위조, 2026-11-16 보안 감사 4장)
 */
function copy(confirmed: boolean | null) {
  return confirmed
    ? {
        title: "탈퇴했어요",
        text: "그동안 무주택자들을 써 주셔서 고마워요. 계정과 관심 공고 · 알림 · 제보를 모두 지웠어요.",
        note: "이 기기에 저장한 조건과 최근 검색어도 지웠어요. 로그인 없이도 공고를 찾아볼 수 있어요.",
      }
    : {
        title: "회원 탈퇴",
        text: "이 화면에서는 탈퇴 결과를 확인할 수 없어요. 탈퇴는 내 정보 → 개인정보 설정에서 본인 확인을 거쳐 진행돼요.",
        note: "로그인 없이도 공고를 찾아볼 수 있어요.",
      };
}

/** 회원 탈퇴 완료 (PC). 백엔드가 탈퇴를 마치고 /withdrawn으로 보내요 */
export function WebWithdrawnState() {
  const { title, text, note } = copy(useForgetAccount());
  return (
    <div className="rounded-card-lg bg-surface flex flex-col items-center gap-[16px] px-[32px] py-[56px] text-center">
      <h1 className="tracking-h1 m-0 text-[26px] font-extrabold">{title}</h1>
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
  const { title, text, note } = copy(useForgetAccount());
  return (
    <section className="rounded-card bg-surface flex flex-col items-center gap-[12px] px-[20px] py-[28px] text-center">
      <h1 className="m-0 text-[22px] font-extrabold">{title}</h1>
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
