import Link from "next/link";
import { cn } from "@/lib/cn";

type SegmentItem = { label: string; selected: boolean } & (
  { href: string; onSelect?: never } | { href?: never; onSelect: () => void }
);

type SegmentProps = {
  items: SegmentItem[];
  label?: string;
  /** 바깥 안쪽 여백: PC 4px, 모바일 3px */
  compact?: boolean;
  className?: string;
  itemClassName?: string;
};

/** 세그먼트: 주거/사업공간, 목록/지도 */
export function Segment({ items, label, compact, className, itemClassName }: SegmentProps) {
  const item = (selected: boolean) =>
    cn(
      "inline-flex min-h-[36px] items-center rounded-[9px] text-[14px] no-underline",
      compact ? "px-[12px]" : "px-[14px]",
      selected
        ? "bg-surface font-bold text-text shadow-seg hover:text-text"
        : "bg-transparent font-semibold text-text-sub hover:text-text-sub",
      itemClassName,
    );

  return (
    <div
      role={items[0]?.href ? undefined : "group"}
      aria-label={label}
      className={cn("bg-fill flex rounded-sm", compact ? "p-[3px]" : "p-[4px]", className)}
    >
      {items.map((it) =>
        it.href ? (
          <Link
            key={it.label}
            href={it.href}
            aria-current={it.selected ? "true" : undefined}
            className={item(it.selected)}
          >
            {it.label}
          </Link>
        ) : (
          <button
            key={it.label}
            type="button"
            aria-pressed={it.selected}
            onClick={it.onSelect}
            className={cn(item(it.selected), "cursor-pointer border-0")}
          >
            {it.label}
          </button>
        ),
      )}
    </div>
  );
}
