import { MTopBar } from "@/shared/layout/MTopBar";
import { MPage, Responsive, WebMain, WebPage } from "@/shared/layout/Responsive";
import { WebHeader } from "@/shared/layout/WebHeader";

/** 빈 상태 · 오류를 화면 가운데 영역에 넣는 틀 (404 · 오류 · 오프라인 화면) */
export function StateFrame({ web, mobile }: { web: React.ReactNode; mobile: React.ReactNode }) {
  return (
    <Responsive
      web={
        <WebPage>
          <WebHeader />
          <WebMain>{web}</WebMain>
        </WebPage>
      }
      mobile={
        <MPage>
          <MTopBar />
          <main
            id="main-content"
            tabIndex={-1}
            className="flex flex-1 flex-col gap-[14px] px-[16px] pt-[24px] pb-[32px]"
          >
            {mobile}
          </main>
        </MPage>
      }
    />
  );
}
