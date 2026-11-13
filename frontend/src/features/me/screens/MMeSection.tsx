"use client";
import { PreparationList } from "@/features/preparations/PreparationList";

import { useSearchParams } from "next/navigation";
import { MBackHeader } from "@/shared/layout/MBackHeader";
import { MPage } from "@/shared/layout/Responsive";
import { InterestsPanel } from "@/features/me/components/InterestsPanel";
import {
  FavoriteList,
  NotificationSettingsPanel,
  ReportPanel,
} from "@/features/me/components/MePanels";
import { reportKindParam } from "@/features/me/tabs";
import { routes } from "@/shared/lib/routes";

export type MeSection = "favorites" | "preparations" | "interests" | "notifications" | "reports";

const titles: Record<MeSection, string> = {
  favorites: "관심 공고",
  preparations: "신청 준비함",
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
      <main
        id="main-content"
        tabIndex={-1}
        className="bg-surface flex flex-1 flex-col gap-[16px] px-[16px] pt-[16px] pb-[32px]"
      >
        {section === "favorites" && <FavoriteList />}
        {section === "preparations" && <PreparationList />}
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
