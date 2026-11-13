"use client";

import { cn } from "@/shared/lib/cn";

/** 혼인·예/아니요를 고르는 공통 선택 버튼. 비어 있으면 아무 값도 고르지 않아요. */
export function Choice<T extends string | boolean>({
  name,
  value,
  options,
  onChange,
}: {
  name: string;
  value: T | undefined;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div role="group" aria-label={name} className="flex flex-wrap gap-[8px]">
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
          className={cn(
            "rounded-control min-h-[44px] cursor-pointer border-2 border-solid px-[14px] text-[14px] font-bold",
            o.value === value
              ? "border-brand bg-brand-soft text-brand-strong"
              : "border-line bg-surface text-text-sub",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** 나 포함 가구원 수와 자녀 수. 미입력과 0명을 구분해요. */
export function CountSelect({
  name,
  value,
  min = 0,
  max,
  onChange,
  className,
}: {
  name: string;
  value: number | null | undefined;
  min?: number;
  max: number;
  onChange: (value: number | undefined) => void;
  className?: string;
}) {
  return (
    <select
      aria-label={name}
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))}
      className={cn(
        "rounded-control border-line bg-surface text-text min-h-[50px] w-full min-w-0 border border-solid px-[14px] text-[16px]",
        className,
      )}
    >
      <option value="">골라 주세요 · 선택</option>
      {Array.from({ length: max - min + 1 }, (_, i) => i + min).map((n) => (
        <option key={n} value={n}>
          {n === 0 ? "없어요 (0명)" : `${n}명`}
        </option>
      ))}
    </select>
  );
}
