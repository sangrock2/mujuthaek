import { useId } from "react";
import { cn } from "@/lib/cn";

type FieldProps = React.InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  help?: React.ReactNode;
  /** 입력칸 오른쪽 안의 단위(만 원, 개월) */
  unit?: string;
  inputClassName?: string;
};

/** 입력칸: 높이 54~56, 둥글기 14, 글자 17px 500. 라벨 15px 700, 도움말 13px */
export function Field({ label, help, unit, className, inputClassName, id, ...props }: FieldProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const helpId = help ? `${inputId}-help` : undefined;

  return (
    <div className={cn("flex flex-col gap-[8px]", className)}>
      <label htmlFor={inputId} className="text-[15px] font-bold">
        {label}
      </label>
      <div className="relative flex">
        <input
          id={inputId}
          aria-describedby={helpId}
          className={cn(
            "rounded-control border-line bg-surface text-text min-h-[54px] w-full border border-solid px-[16px] text-[17px] font-medium",
            unit && "pr-[64px]",
            inputClassName,
          )}
          {...props}
        />
        {unit && (
          <span className="text-text-sub pointer-events-none absolute top-1/2 right-[16px] -translate-y-1/2 text-[16px] font-semibold">
            {unit}
          </span>
        )}
      </div>
      {help && (
        <span id={helpId} className="text-text-sub text-[13px]">
          {help}
        </span>
      )}
    </div>
  );
}
