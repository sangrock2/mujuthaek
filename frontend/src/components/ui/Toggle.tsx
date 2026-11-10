"use client";

import { cn } from "@/lib/cn";

type ToggleProps = {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  className?: string;
};

/** 토글 스위치 52×32, 손잡이 26 */
export function Toggle({ checked, onChange, label, className }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn(
        "rounded-pill flex h-[32px] w-[52px] flex-none cursor-pointer border-0 p-[3px]",
        checked ? "bg-brand justify-end" : "bg-off justify-start",
        className,
      )}
    >
      <span className="rounded-pill size-[26px] bg-white shadow-[0_1px_3px_rgba(25,31,40,0.25)]" />
    </button>
  );
}
