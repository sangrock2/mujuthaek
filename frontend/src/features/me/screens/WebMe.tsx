"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useLogout, useSession } from "@/features/auth/session";
import { useFavorites } from "@/features/favorites/queries";
import { useMyReports } from "@/features/me/api";
import { InterestsPanel } from "@/features/me/components/InterestsPanel";
import {
  MeNavigation,
  meTabHref,
  meTitles,
  type MeDestination,
} from "@/features/me/components/MeNavigation";
import { MeOverview } from "@/features/me/components/MeOverview";
import {
  FavoriteList,
  NotificationSettingsPanel,
  ReportPanel,
} from "@/features/me/components/MePanels";
import {
  ConditionEditLink,
  ConditionsPanel,
  PrivacyPanel,
} from "@/features/me/components/MeSettingsPanels";
import {
  meTabs,
  reportCodeParam,
  reportKindParam,
  reportScreenParam,
  type MeTab,
} from "@/features/me/tabs";
import { PreparationList } from "@/features/preparations/PreparationList";
import { WebPage } from "@/shared/layout/Responsive";
import { WebHeader } from "@/shared/layout/WebHeader";
import { cn } from "@/shared/lib/cn";
import { routes } from "@/shared/lib/routes";

export function WebMe({ initialTab }: { initialTab?: MeTab }) {
  const { logout, logoutError } = useLogout();
  const { data: session } = useSession();
  const router = useRouter();
  const params = useSearchParams();
  const favorites = useFavorites();
  const reports = useMyReports();
  const replies = reports.items.filter((report) => report.reply).length;
  const favoriteCount = favorites.loggedIn ? favorites.items.length : undefined;
  const fromUrl = params.get("tab");
  const tab = meTabs.find((option) => option === fromUrl) ?? initialTab ?? "overview";
  const framed = tab === "preparations" || tab === "reports";

  function selectTab(destination: MeDestination) {
    if (destination === tab) return;
    window.history.replaceState(null, "", meTabHref(destination));
  }

  return (
    <WebPage>
      <WebHeader mode="home" active="me" />
      <main
        id="main-content"
        tabIndex={-1}
        className="mx-auto grid w-full max-w-[1180px] grid-cols-[248px_minmax(0,1fr)] items-start gap-[24px] px-[26px] pt-[34px] pb-[64px]"
      >
        <aside className="flex min-w-0 flex-col gap-[12px]">
          <MeNavigation
            current={tab}
            onSelect={initialTab ? undefined : selectTab}
            favorites={favoriteCount}
            replies={replies}
          />
          {session && (
            <div className="flex flex-col items-start px-[12px]">
              <button
                type="button"
                onClick={() =>
                  void logout().then((ok) => {
                    if (ok) router.push(routes.main);
                  })
                }
                className="text-text-sub min-h-[44px] cursor-pointer text-[14px] font-bold"
              >
                로그아웃
              </button>
              {logoutError && (
                <p role="alert" className="text-danger text-[13px]">
                  {logoutError}
                </p>
              )}
            </div>
          )}
        </aside>

        <section aria-labelledby="me-title" className="flex min-w-0 flex-col gap-[16px]">
          <div className="flex min-h-[54px] items-center justify-between gap-[12px]">
            <h1 id="me-title" className="tracking-h1 m-0 text-[29px] font-extrabold">
              {meTitles[tab]}
            </h1>
            {tab === "conditions" && <ConditionEditLink />}
          </div>
          <div
            className={cn(
              "min-w-0",
              framed && "rounded-card border-line-soft bg-surface border p-[24px]",
            )}
          >
            {tab === "overview" && <MeOverview />}
            {tab === "conditions" && <ConditionsPanel />}
            {tab === "favorites" && <FavoriteList />}
            {tab === "preparations" && <PreparationList />}
            {tab === "interests" && <InterestsPanel />}
            {tab === "notifications" && <NotificationSettingsPanel />}
            {tab === "privacy" && <PrivacyPanel />}
            {tab === "reports" && (
              <ReportPanel
                initialKind={reportKindParam(params.get("kind"))}
                screen={reportScreenParam(params.get("from"))}
                context={reportCodeParam(params.get("code"))}
              />
            )}
          </div>
        </section>
      </main>
    </WebPage>
  );
}
