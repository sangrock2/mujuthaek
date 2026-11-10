import { cn } from "@/lib/cn";

type FilterChipProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  selected: boolean;
  /** 흰 카드 위면 기본 바탕이 회색(#F2F4F6), 회색 페이지 위면 흰색 */
  onCard?: boolean;
};

/** 필터 칩: 알약, 선택은 #191F28 바탕 + 흰 글자 */
export function FilterChip({ selected, onCard, className, ...props }: FilterChipProps) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      className={cn(
        "rounded-pill inline-flex min-h-[40px] cursor-pointer items-center border-0 px-[16px] text-[14px]",
        selected
          ? "bg-text font-bold text-white"
          : cn("text-text-sub font-semibold", onCard ? "bg-fill" : "bg-surface"),
        className,
      )}
      {...props}
    />
  );
}

/** 정보 태그(역세권 등) */
export function InfoTag({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "rounded-tag bg-neutral-bg text-neutral-text px-[8px] py-[3px] text-[12px] font-semibold",
        className,
      )}
    >
      {children}
    </span>
  );
}

type SelectChipProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { selected: boolean };

/** 선택형 칩(조건 입력): 2px 테두리, 선택은 초록 테두리 + 연한 초록 바탕 */
export function SelectChip({ selected, className, ...props }: SelectChipProps) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      className={cn(
        "rounded-control min-h-[54px] cursor-pointer border-2 border-solid text-[16px] font-bold",
        selected
          ? "border-brand bg-brand-soft text-brand-strong"
          : "border-line bg-surface text-text",
        className,
      )}
      {...props}
    />
  );
}
