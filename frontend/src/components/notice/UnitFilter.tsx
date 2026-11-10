import { cn } from "@/lib/cn";

/** 공급 주택 목록 필터: 전체 / 신청 가능만 (PC) */
export function WebUnitFilter({
  onlyOk,
  setOnlyOk,
  countAll,
  countOk,
  wide,
}: {
  onlyOk: boolean;
  setOnlyOk: (v: boolean) => void;
  countAll: number;
  countOk: number;
  /** 주택목록 공고는 안쪽 여백이 14px */
  wide?: boolean;
}) {
  const item = (on: boolean) =>
    cn(
      "min-h-[36px] cursor-pointer rounded-[9px] border-0 text-[14px] font-bold",
      wide ? "px-[14px]" : "px-[12px]",
      on ? "bg-surface text-text shadow-seg" : "text-text-sub bg-transparent",
    );
  return (
    <div role="group" aria-label="목록 필터" className="bg-fill flex rounded-sm p-[4px]">
      <button
        type="button"
        aria-pressed={!onlyOk}
        onClick={() => setOnlyOk(false)}
        className={item(!onlyOk)}
      >
        전체 {countAll}
      </button>
      <button
        type="button"
        aria-pressed={onlyOk}
        onClick={() => setOnlyOk(true)}
        className={item(onlyOk)}
      >
        신청 가능만 {countOk}
      </button>
    </div>
  );
}
