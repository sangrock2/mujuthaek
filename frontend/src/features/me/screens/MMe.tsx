"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useSession } from "@/features/auth/session";
import { useFavorites } from "@/features/favorites/queries";
import { useMyReports } from "@/features/me/api";
import { MeNavigation } from "@/features/me/components/MeNavigation";
import { MeOverview } from "@/features/me/components/MeOverview";
import { MeLogout } from "@/features/me/components/MeLogout";
import { meTabs, type MeTab } from "@/features/me/tabs";
import { MTabBar } from "@/shared/layout/MTabBar";
import { MTopBar } from "@/shared/layout/MTopBar";
import { MPage } from "@/shared/layout/Responsive";
import { routes } from "@/shared/lib/routes";

export function MMe() {
  const router = useRouter();
  const params = useSearchParams();
  const { data: session } = useSession();
  const favorites = useFavorites();
  const reports = useMyReports();
  const replies = reports.items.filter((report) => report.reply).length;
  const favoriteCount = favorites.loggedIn ? favorites.items.length : undefined;
  const tab = params.get("tab") as MeTab | null;

  useEffect(() => {
    if (!tab || !meTabs.includes(tab) || window.matchMedia("(min-width: 1024px)").matches) return;
    const rest = new URLSearchParams(params.toString());
    rest.delete("tab");
    router.replace(`${routes.me}/${tab}${rest.size ? `?${rest.toString()}` : ""}`);
  }, [tab, params, router]);

  return (
    <MPage className="stitch-surface h-dvh min-h-0 overflow-hidden [&>header]:shrink-0 [&>nav]:shrink-0">
      <MTopBar mode="home" />
      <main id="main-content" tabIndex={-1} className="flex min-h-0 flex-1 flex-col">
        <h1 className="tracking-h1 m-0 shrink-0 px-4 pt-4 pb-3 text-[18px] font-bold">
          마이페이지
        </h1>
        <div
          role="region"
          aria-label="마이페이지 내용"
          tabIndex={0}
          className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto overscroll-contain px-4 pb-4 focus-visible:outline-offset-[-3px]"
        >
          <MeOverview mobile />
          <MeNavigation mobile favorites={favoriteCount} replies={replies} />
        </div>
        {session && (
          <div className="border-line-soft bg-surface shrink-0 border-t px-4 py-1.5">
            <MeLogout />
          </div>
        )}
      </main>
      <MTabBar mode="home" current={routes.me} />
    </MPage>
  );
}
