"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ChevronRight, Lock, User } from "lucide-react";
import { ContactEmailCard } from "@/components/auth/ContactEmailParts";
import { WebHeader } from "@/components/layout/WebHeader";
import { WebPage } from "@/components/layout/Responsive";
import { InterestsPanel } from "@/components/me/InterestsPanel";
import { FavoriteList, NotificationSettingsPanel, ReportPanel } from "@/components/me/MePanels";
import { WithdrawButton } from "@/components/me/WithdrawButton";
import { Toggle } from "@/components/ui/Toggle";
import { providerLabel, useLogout, useSession } from "@/features/auth/session";
import { clearConditions, setSaveOnDevice } from "@/features/conditions/store";
import { StoredInfoList, saveOnDeviceNote } from "@/components/me/StoredInfo";
import { useConditionSummary } from "@/features/conditions/useConditionSummary";
import { useFavorites } from "@/features/favorites/queries";
import { useMyReports } from "@/features/me/api";
import { meTabs, reportKindParam, type MeTab } from "@/features/me/tabs";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";

const titles: Record<MeTab, string> = {
  conditions: "내 조건",
  favorites: "관심 공고",
  interests: "관심 조건",
  notifications: "알림 설정",
  privacy: "개인정보 설정",
  reports: "제보하기",
};

const supportLinks = [
  { label: "공지사항", href: routes.announcements },
  { label: "자주 묻는 질문", href: routes.faq },
  { label: "이용약관", href: routes.terms },
  { label: "개인정보처리방침", href: routes.privacy, strong: true },
];

const grayButton =
  "bg-fill text-text min-h-[48px] cursor-pointer rounded-sm border-0 px-[16px] text-[15px] font-bold";

/** 내 정보 (웹). 탭은 주소의 ?tab=으로도 열려요 (예: /me?tab=reports) */
export function WebMe({ initialTab }: { initialTab?: MeTab }) {
  const logout = useLogout();
  const router = useRouter();
  const params = useSearchParams();
  const { data: session } = useSession();
  const favorites = useFavorites();
  const reports = useMyReports();
  const replies = reports.items.filter((r) => r.reply).length;
  const fromUrl = params.get("tab");
  const urlTab = meTabs.includes(fromUrl as MeTab) ? (fromUrl as MeTab) : null;
  // 주소의 ?tab=이 먼저예요: /me/favorites에서 탭을 바꾸면 주소가 /me?tab=…가 되는데, 앞으로 가기로 돌아오면 그 화면이 다시 그려져요
  const [tab, setTabState] = useState<MeTab>(urlTab ?? initialTab ?? "conditions");
  // 링크로 주소의 탭이 바뀌면(헤더 「내 정보」 → /me, 「내 제보 보기」 → ?tab=reports) 화면 탭도 따라가요 (렌더 중 상태 맞추기)
  const [seenUrlTab, setSeenUrlTab] = useState(urlTab);
  if (urlTab !== seenUrlTab) {
    setSeenUrlTab(urlTab);
    setTabState(urlTab ?? initialTab ?? "conditions");
  }
  // 탭은 화면 상태만 바꾸고 주소는 history로만 고쳐요 (router.replace는 서버에 페이지를 다시 받아 와 탭마다 늦어요).
  // Next가 history 변경을 useSearchParams에 반영해서 새로 고침·뒤로 가기에도 그 탭이 열려요
  const setTab = (t: MeTab) => {
    setTabState(t);
    window.history.replaceState(null, "", `${routes.me}?tab=${t}`);
  };
  const conditions = useConditionSummary();
  const saveOnDevice = conditions.status === "ready" ? conditions.saveOnDevice : true;

  const menu: { key: MeTab; label: string; count: string }[] = [
    { key: "conditions", label: "내 조건", count: "" },
    {
      key: "favorites",
      label: "관심 공고",
      count: favorites.loggedIn ? `${favorites.items.length}개` : "",
    },
    { key: "interests", label: "관심 조건", count: "" },
    { key: "notifications", label: "알림 설정", count: "" },
    { key: "privacy", label: "개인정보 설정", count: "" },
    { key: "reports", label: "제보하기", count: replies ? `답변 ${replies}` : "" },
  ];

  return (
    <WebPage>
      <WebHeader mode="home" active="me" />
      <main className="mx-auto box-border flex w-full max-w-[1200px] flex-1 flex-wrap items-start gap-[24px] px-[32px] pt-[40px] pb-[72px]">
        <div className="flex min-w-0 flex-[1_1_260px] flex-col gap-[16px]">
          <section
            aria-label="계정"
            className="rounded-card bg-surface flex flex-col gap-[14px] p-[22px]"
          >
            <div className="flex items-center gap-[12px]">
              <span className="rounded-pill bg-brand-soft text-brand flex size-[52px] flex-none items-center justify-center">
                <User size={26} strokeWidth={1.8} aria-hidden />
              </span>
              <span className="flex min-w-0 flex-col gap-[2px]">
                <span className="text-[18px] font-extrabold">
                  {session ? `${session.nickname}님` : "로그인하지 않았어요"}
                </span>
                <span className="text-text-sub truncate text-[14px]">
                  {session
                    ? (session.email ?? "연락용 이메일 없음")
                    : "로그인하면 관심 공고·알림을 받을 수 있어요"}
                </span>
              </span>
            </div>
            <div className="flex items-center justify-between">
              {session ? (
                <>
                  <span className="rounded-badge bg-fill text-text-sub px-[10px] py-[5px] text-[13px] font-semibold">
                    {session.providers.map((p) => providerLabel[p] ?? p).join(" · ")}로 로그인
                  </span>
                  <button
                    type="button"
                    onClick={() => void logout().then(() => router.push(routes.main))}
                    className="text-text-sub hover:text-text-sub inline-flex min-h-[44px] cursor-pointer items-center border-0 bg-transparent p-0 text-[14px] font-semibold"
                  >
                    로그아웃
                  </button>
                </>
              ) : (
                <Link
                  href={routes.login}
                  className="bg-brand inline-flex min-h-[44px] items-center rounded-sm px-[16px] text-[15px] font-bold text-white no-underline hover:text-white"
                >
                  로그인하기
                </Link>
              )}
            </div>
          </section>

          <nav
            aria-label="내 정보 메뉴"
            className="rounded-card bg-surface flex flex-col gap-[2px] p-[8px]"
          >
            {menu.map((m) => {
              const on = m.key === tab;
              return (
                <button
                  key={m.key}
                  type="button"
                  aria-current={on ? "page" : undefined}
                  onClick={() => setTab(m.key)}
                  className={cn(
                    "rounded-control flex min-h-[52px] cursor-pointer items-center justify-between gap-[8px] border-0 px-[14px] text-left",
                    on ? "bg-brand-soft text-brand-strong" : "text-text bg-transparent",
                  )}
                >
                  <span className={cn("text-[16px]", on ? "font-extrabold" : "font-semibold")}>
                    {m.label}
                  </span>
                  <span className="text-text-sub text-[14px]">{m.count}</span>
                </button>
              );
            })}
            {/* 사업 정보는 따로 입력 화면이 있어요 (모바일 내 정보와 같은 바로가기) */}
            <Link
              href={routes.bizOnboarding}
              className="rounded-control text-text hover:text-text flex min-h-[52px] items-center justify-between gap-[8px] px-[14px] text-[16px] font-semibold no-underline"
            >
              사업 정보
              <span className="text-text-sub text-[14px]">사업공간 판정</span>
            </Link>
          </nav>

          <nav
            aria-label="고객센터"
            className="rounded-card bg-surface flex flex-col gap-[2px] p-[8px]"
          >
            {supportLinks.map((l) => (
              <Link
                key={l.label}
                href={l.href}
                className={cn(
                  "rounded-control text-text hover:text-text flex min-h-[48px] items-center justify-between px-[14px] text-[15px] no-underline",
                  l.strong ? "font-bold" : "font-medium",
                )}
              >
                {l.label}
                <ChevronRight size={16} className="text-text-tertiary" aria-hidden />
              </Link>
            ))}
          </nav>
        </div>

        <section
          aria-label={titles[tab]}
          className="rounded-card-lg bg-surface flex min-w-0 flex-[999_1_600px] flex-col gap-[22px] p-[30px]"
        >
          <div className="flex items-center justify-between gap-[12px]">
            <h1 className="tracking-h1 m-0 text-[26px] font-extrabold">{titles[tab]}</h1>
            {tab === "conditions" && (
              <Link
                href={routes.profile}
                className="bg-fill text-text hover:text-text inline-flex min-h-[44px] items-center gap-[4px] rounded-sm px-[14px] text-[15px] font-bold no-underline"
              >
                조건 수정
              </Link>
            )}
          </div>

          {tab === "conditions" && (
            <div className="flex flex-col gap-[16px]">
              {conditions.status === "ready" && !conditions.hasConditions ? (
                <span className="rounded-tile bg-bg text-text-sub px-[16px] py-[18px] text-[15px]">
                  아직 입력한 조건이 없어요. 조건을 입력하면 이 기기에 저장해 둘게요.
                </span>
              ) : (
                <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-[10px]">
                  {conditions.status === "ready" &&
                    conditions.rows.map((c) => (
                      <div key={c.k} className="rounded-tile bg-bg px-[16px] py-[14px]">
                        <dt className="text-text-sub text-[13px]">{c.k}</dt>
                        <dd
                          className={cn(
                            "m-0 mt-[4px] text-[16px] font-bold",
                            c.muted ? "text-text-sub" : "text-text",
                          )}
                        >
                          {c.v}
                        </dd>
                      </div>
                    ))}
                </dl>
              )}
              <span className="text-text-sub inline-flex items-center gap-[6px] text-[14px]">
                <Lock size={16} aria-hidden />
                소득·자산은 저장하지 않아요. 판정할 때만 입력해요
              </span>
            </div>
          )}

          {tab === "favorites" && <FavoriteList />}
          {tab === "interests" && <InterestsPanel />}
          {tab === "notifications" && <NotificationSettingsPanel />}

          {tab === "privacy" && (
            <div className="flex flex-col gap-[16px]">
              <div className="bg-brand-soft flex items-center justify-between gap-[16px] rounded-[20px] px-[22px] py-[20px]">
                <span className="flex flex-col gap-[4px]">
                  <span className="text-brand-strong text-[17px] font-extrabold">
                    이 기기에 조건 저장
                  </span>
                  <span className="text-brand-strong text-[14px] leading-[1.6]">
                    {saveOnDeviceNote(saveOnDevice)}
                  </span>
                </span>
                <Toggle
                  checked={saveOnDevice}
                  onChange={setSaveOnDevice}
                  label="이 기기에 조건 저장"
                />
              </div>
              <ContactEmailCard className="border-line-soft border-b border-solid pb-[16px]" />
              <StoredInfoList />
              <button
                type="button"
                onClick={clearConditions}
                disabled={!conditions.hasConditions}
                className={cn(
                  grayButton,
                  "disabled:text-text-sub self-start disabled:cursor-default",
                )}
              >
                저장한 조건 모두 지우기
              </button>
              {session && <WithdrawButton />}
            </div>
          )}

          {tab === "reports" && (
            <ReportPanel
              initialKind={reportKindParam(params.get("kind"))}
              screen={params.get("from") ?? undefined}
              context={params.get("code") ?? undefined}
            />
          )}
        </section>
      </main>
    </WebPage>
  );
}
