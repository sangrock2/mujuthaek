"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ChevronRight, Lock, User } from "lucide-react";
import { ContactEmailCard } from "@/components/auth/ContactEmailParts";
import { WithdrawButton } from "@/components/me/WithdrawButton";
import { StoredInfoList, saveOnDeviceNote } from "@/components/me/StoredInfo";
import { MTabBar } from "@/components/layout/MTabBar";
import { MTopBar } from "@/components/layout/MTopBar";
import { MPage } from "@/components/layout/Responsive";
import { Toggle } from "@/components/ui/Toggle";
import { clearConditions, setSaveOnDevice } from "@/features/conditions/store";
import { useConditionSummary } from "@/features/conditions/useConditionSummary";
import { useFavorites } from "@/features/favorites/queries";
import { useMyReports } from "@/features/me/api";
import { cn } from "@/lib/cn";
import { providerLabel, useLogout, useSession } from "@/features/auth/session";
import { routes } from "@/lib/routes";

const row =
  "rounded-tile text-text hover:text-text flex min-h-[56px] items-center gap-[12px] px-[14px] no-underline";

const supportLinks = [
  { label: "공지사항", href: routes.announcements },
  { label: "자주 묻는 질문", href: routes.faq },
  { label: "이용약관", href: routes.terms },
  { label: "개인정보처리방침", href: routes.privacy, strong: true },
];

function RowInner({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <>
      <span className="flex-1 text-[16px] font-semibold">{label}</span>
      <span className={cn("text-[14px]", accent ? "text-brand-strong font-bold" : "text-text-sub")}>
        {value}
      </span>
      <ChevronRight size={18} className="text-text-tertiary" aria-hidden />
    </>
  );
}

export function MMe() {
  const logout = useLogout();
  const router = useRouter();
  const params = useSearchParams();
  const { data: session } = useSession();
  const favorites = useFavorites();
  const reports = useMyReports();
  const replies = reports.items.filter((r) => r.reply).length;
  // 웹 주소(/me?tab=reports …)로 들어오면 모바일 세부 화면으로. PC 폭(lg, 1024px 이상)에서는 이 화면이 숨어 있어도
  // 그려져 있어서(Responsive), 여기서 옮기면 웹 탭을 누를 때마다 /me/{tab}으로 다시 이동해 버벅이고 탭이 되돌아가요
  const tab = params.get("tab");
  useEffect(() => {
    if (window.matchMedia("(min-width: 1024px)").matches) return;
    if (tab && ["favorites", "interests", "notifications", "reports"].includes(tab)) {
      const rest = new URLSearchParams(params.toString());
      rest.delete("tab");
      router.replace(`${routes.me}/${tab}${rest.size ? `?${rest.toString()}` : ""}`);
    }
  }, [tab, params, router]);
  const conditions = useConditionSummary();
  const saveOnDevice = conditions.status === "ready" ? conditions.saveOnDevice : true;

  return (
    <MPage>
      <MTopBar mode="home" />
      <main className="flex flex-1 flex-col gap-[12px] px-[16px] pt-[20px] pb-[28px]">
        <section
          aria-label="계정"
          className="rounded-card bg-surface flex items-center gap-[14px] p-[20px]"
        >
          <span className="rounded-pill bg-brand-soft text-brand flex size-[52px] flex-none items-center justify-center">
            <User size={26} aria-hidden />
          </span>
          <span className="flex min-w-0 flex-1 flex-col gap-[2px]">
            <span className="text-[19px] font-extrabold">
              {session ? `${session.nickname}님` : "로그인하지 않았어요"}
            </span>
            <span className="text-text-sub text-[14px]">
              {session ? (
                <>
                  {session.email ?? "연락용 이메일 없음"} ·{" "}
                  {session.providers.map((p) => providerLabel[p] ?? p).join(" · ")}
                </>
              ) : (
                <Link href={routes.login} className="text-brand font-bold">
                  로그인하기
                </Link>
              )}
            </span>
          </span>
        </section>

        <ContactEmailCard className="rounded-card bg-surface px-[20px] py-[18px]" />

        <section
          aria-labelledby="cond-h"
          className="rounded-card bg-surface flex flex-col gap-[12px] px-[20px] py-[18px]"
        >
          <div className="flex items-center justify-between">
            <h2 id="cond-h" className="m-0 text-[17px] font-extrabold">
              내 조건
            </h2>
            <Link
              href={routes.profile}
              className="inline-flex min-h-[44px] items-center text-[14px] font-bold no-underline"
            >
              수정
            </Link>
          </div>
          {conditions.status === "ready" && !conditions.hasConditions && (
            <span className="text-text-sub text-[14px]">
              아직 입력한 조건이 없어요. 조건을 입력하면 이 기기에 저장해 둘게요.
            </span>
          )}
          <div className="flex flex-wrap gap-[6px]">
            {(conditions.status === "ready" ? conditions.shortChips : []).map((c) => (
              <span
                key={c}
                className="rounded-pill bg-fill text-text-sub px-[12px] py-[6px] text-[14px] font-semibold"
              >
                {c}
              </span>
            ))}
          </div>
          <span className="text-text-sub flex items-center gap-[6px] text-[13px]">
            <Lock size={15} aria-hidden />
            소득·자산은 저장하지 않아요
          </span>
        </section>

        <nav aria-label="내 정보 메뉴" className="rounded-card bg-surface flex flex-col p-[6px]">
          <Link href={`${routes.me}/favorites`} className={row}>
            <RowInner
              label="관심 공고"
              value={favorites.loggedIn ? String(favorites.items.length) : ""}
            />
          </Link>
          <Link href={`${routes.me}/interests`} className={row}>
            <RowInner label="관심 조건" value="새 공고 알림" />
          </Link>
          <Link href={`${routes.me}/notifications`} className={row}>
            <RowInner label="알림 설정" value="" />
          </Link>
          <div className={cn(row, "justify-between")}>
            <span className="flex flex-col gap-[2px]">
              <span className="text-[16px] font-semibold">이 기기에 조건 저장</span>
              <span className="text-text-sub text-[13px]">{saveOnDeviceNote(saveOnDevice)}</span>
            </span>
            <Toggle checked={saveOnDevice} onChange={setSaveOnDevice} label="이 기기에 조건 저장" />
          </div>
          {conditions.status === "ready" && conditions.hasConditions && (
            <button
              type="button"
              onClick={clearConditions}
              className={cn(row, "cursor-pointer border-0 bg-transparent text-left")}
            >
              <span className="flex-1 text-[16px] font-semibold">저장한 조건 지우기</span>
            </button>
          )}
          <Link href={routes.bizOnboarding} className={row}>
            <RowInner label="사업 정보" value="" />
          </Link>
          <Link href={`${routes.me}/reports`} className={row}>
            <RowInner
              label="제보하기 · 내 제보"
              value={replies ? `답변 ${replies}` : ""}
              accent={replies > 0}
            />
          </Link>
        </nav>

        <section aria-label="저장된 정보" className="rounded-card bg-surface px-[18px] py-[14px]">
          <StoredInfoList compact />
        </section>

        <nav aria-label="고객센터" className="rounded-card bg-surface flex flex-col p-[6px]">
          {supportLinks.map((l) => (
            <Link
              key={l.label}
              href={l.href}
              className={cn(
                "rounded-tile text-text hover:text-text flex min-h-[52px] items-center justify-between px-[14px] text-[15px] no-underline",
                l.strong && "font-bold",
              )}
            >
              {l.label}
              <ChevronRight size={18} className="text-text-tertiary" aria-hidden />
            </Link>
          ))}
        </nav>

        {session && (
          <div className="flex flex-col gap-[4px] px-[8px]">
            <button
              type="button"
              onClick={() => void logout().then(() => router.push(routes.main))}
              className="text-text-sub hover:text-text-sub inline-flex min-h-[44px] cursor-pointer items-center self-start border-0 bg-transparent p-0 text-[14px] font-semibold"
            >
              로그아웃
            </button>
            <WithdrawButton />
          </div>
        )}
      </main>
      <MTabBar mode="home" current={routes.me} />
    </MPage>
  );
}
