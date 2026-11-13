import Link from "next/link";
import { ChevronLeft } from "lucide-react";

type MBackHeaderProps = {
  title: string;
  backHref: string;
  /** 오른쪽 버튼들 */
  actions?: React.ReactNode;
};

/** 상세 · 입력 화면 상단: 뒤로가기 + 제목 */
export function MBackHeader({ title, backHref, actions }: MBackHeaderProps) {
  return (
    <header className="border-line-soft bg-surface sticky top-0 z-[2] flex h-[56px] items-center gap-[2px] border-b border-solid px-[6px]">
      <Link
        href={backHref}
        aria-label="뒤로"
        className="text-text hover:text-text inline-flex size-[44px] flex-none items-center justify-center rounded-sm"
      >
        <ChevronLeft size={24} aria-hidden />
      </Link>
      <h1 className="tracking-title m-0 flex-1 truncate text-[18px] font-extrabold">{title}</h1>
      {actions}
    </header>
  );
}

/** 하단 고정 버튼 영역: 위 1px 선, 아래 여백 28px */
export function MBottomActions({ children }: { children: React.ReactNode }) {
  return (
    <div className="border-line bg-surface sticky bottom-0 flex gap-[8px] border-t border-solid px-[16px] pt-[12px] pb-[28px]">
      {children}
    </div>
  );
}
