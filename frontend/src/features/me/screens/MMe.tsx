"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useLogout, useSession } from "@/features/auth/session";
import { useFavorites } from "@/features/favorites/queries";
import { useMyReports } from "@/features/me/api";
import { MeNavigation } from "@/features/me/components/MeNavigation";
import { MeOverview } from "@/features/me/components/MeOverview";
import { meTabs, type MeTab } from "@/features/me/tabs";
import { MTabBar } from "@/shared/layout/MTabBar";
import { MTopBar } from "@/shared/layout/MTopBar";
import { MPage } from "@/shared/layout/Responsive";
import { routes } from "@/shared/lib/routes";

export function MMe() {
  const { logout, logoutError } = useLogout();
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
    <MPage>
      <MTopBar mode="home" />
      <main
        id="main-content"
        tabIndex={-1}
        className="flex flex-1 flex-col gap-[12px] px-[16px] pt-[20px] pb-[28px]"
      >
        <h1 className="tracking-h1 m-0 mb-[2px] text-[24px] font-extrabold">마이페이지</h1>
        <MeOverview mobile />
        <MeNavigation mobile favorites={favoriteCount} replies={replies} />
        {session && (
          <div className="flex flex-col items-start px-[8px]">
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
      </main>
      <MTabBar mode="home" current={routes.me} />
    </MPage>
  );
}
