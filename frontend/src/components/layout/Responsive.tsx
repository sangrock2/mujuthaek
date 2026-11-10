import { cn } from "@/lib/cn";

/** PC(Web*) / 모바일(M*) 화면을 따로 그리고 폭에 따라 하나만 보여줘요 */
export function Responsive({ web, mobile }: { web: React.ReactNode; mobile: React.ReactNode }) {
  return (
    <>
      <div className="hidden min-h-full flex-1 flex-col lg:flex">{web}</div>
      <div className="flex min-h-full flex-1 flex-col lg:hidden">{mobile}</div>
    </>
  );
}

/** PC 화면 바탕: 회색 페이지 + 본문 최대 1200px */
export function WebPage({ children }: { children: React.ReactNode }) {
  return <div className="bg-bg text-text flex min-h-screen w-full flex-col">{children}</div>;
}

export function WebMain({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <main
      className={cn(
        "mx-auto box-border flex w-full max-w-[1200px] flex-1 flex-col gap-[24px] px-[32px] pt-[40px] pb-[72px]",
        className,
      )}
    >
      {children}
    </main>
  );
}

/** 모바일 화면 바탕 */
export function MPage({ children }: { children: React.ReactNode }) {
  return <div className="bg-bg text-text flex min-h-screen w-full flex-col">{children}</div>;
}
