"use client";

import { useSearchParams } from "next/navigation";
import { useSession } from "@/features/auth/session";
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
import { MeLogout } from "@/features/me/components/MeLogout";
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

export function WebMe({ initialTab }: { initialTab?: MeTab }) {
  const { data: session } = useSession();
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
    <WebPage className="stitch-surface h-dvh min-h-0 overflow-hidden [&>header]:shrink-0">
      <WebHeader mode="home" active="me" />
      <main
        id="main-content"
        tabIndex={-1}
        className="mx-auto grid min-h-0 w-full max-w-[1180px] flex-1 grid-cols-[248px_minmax(0,1fr)] gap-[24px] px-[26px] py-[20px]"
      >
        <aside aria-label="내 정보 메뉴 영역" className="flex min-h-0 min-w-0 flex-col">
          <MeNavigation
            current={tab}
            onSelect={initialTab ? undefined : selectTab}
            favorites={favoriteCount}
            replies={replies}
            footer={session && <MeLogout />}
          />
        </aside>

        <div className="flex min-h-0 min-w-0 flex-col gap-[16px]">
          {tab !== "overview" && (
            <div className="flex min-h-[54px] shrink-0 items-center justify-between gap-[12px]">
              <h1 className="tracking-h1 m-0 text-[29px] font-extrabold">{meTitles[tab]}</h1>
              {tab === "conditions" && <ConditionEditLink />}
            </div>
          )}
          <div
            key={tab}
            role="region"
            aria-label={`${meTitles[tab]} 내용`}
            tabIndex={0}
            className="min-h-0 min-w-0 flex-1 overflow-y-auto overscroll-contain p-0.5"
          >
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
          </div>
        </div>
      </main>
    </WebPage>
  );
}
