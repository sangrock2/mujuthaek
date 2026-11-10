"use client";

import { useSearchParams } from "next/navigation";
import { MBackHeader } from "@/components/layout/MBackHeader";
import { MPage } from "@/components/layout/Responsive";
import { InterestsPanel } from "@/components/me/InterestsPanel";
import { FavoriteList, NotificationSettingsPanel, ReportPanel } from "@/components/me/MePanels";
import { reportKindParam } from "@/features/me/tabs";
import { routes } from "@/lib/routes";

export type MeSection = "favorites" | "interests" | "notifications" | "reports";

const titles: Record<MeSection, string> = {
  favorites: "관심 공고",
  interests: "관심 조건",
  notifications: "알림 설정",
  reports: "제보하기",
};

/** 내 정보의 세부 화면 (모바일) */
export function MMeSection({ section }: { section: MeSection }) {
  const params = useSearchParams();
  return (
    <MPage>
      <MBackHeader title={titles[section]} backHref={routes.me} />
      <main className="bg-surface flex flex-1 flex-col gap-[16px] px-[16px] pt-[16px] pb-[32px]">
        {section === "favorites" && <FavoriteList />}
        {section === "interests" && <InterestsPanel />}
        {section === "notifications" && <NotificationSettingsPanel />}
        {section === "reports" && (
          <ReportPanel
            initialKind={reportKindParam(params.get("kind"))}
            screen={params.get("from") ?? undefined}
            context={params.get("code") ?? undefined}
          />
        )}
      </main>
    </MPage>
  );
}
