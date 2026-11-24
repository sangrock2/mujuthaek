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
import { meTitles } from "@/features/me/components/MeNavigation";
import {
  ConditionEditLink,
  ConditionsPanel,
  PrivacyPanel,
} from "@/features/me/components/MeSettingsPanels";
import {
  reportKindParam,
  reportScreenParam,
  reportCodeParam,
  type MeTab,
} from "@/features/me/tabs";
import { cn } from "@/shared/lib/cn";
import { routes } from "@/shared/lib/routes";
/** 내 정보의 세부 화면 (모바일) */
export function MMeSection({ section }: { section: MeTab }) {
  const params = useSearchParams();
  return (
    <MPage className="stitch-surface">
      <MBackHeader
        title={meTitles[section]}
        backHref={routes.me}
        actions={section === "conditions" ? <ConditionEditLink /> : undefined}
      />
      <main
        id="main-content"
        tabIndex={-1}
        className={cn(
          "flex flex-1 flex-col gap-[16px] px-[16px] pt-[16px] pb-[32px]",
          (section === "preparations" || section === "reports") && "bg-surface",
        )}
      >
        {section === "conditions" && <ConditionsPanel />}
        {section === "privacy" && <PrivacyPanel />}
        {section === "favorites" && <FavoriteList />}
        {section === "preparations" && <PreparationList />}
        {section === "interests" && <InterestsPanel />}
        {section === "notifications" && <NotificationSettingsPanel />}
        {section === "reports" && (
          <ReportPanel
            initialKind={reportKindParam(params.get("kind"))}
            screen={reportScreenParam(params.get("from"))}
            context={reportCodeParam(params.get("code"))}
          />
        )}
      </main>
    </MPage>
  );
}
