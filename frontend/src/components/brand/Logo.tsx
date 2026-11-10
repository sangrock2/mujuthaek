import { cn } from "@/lib/cn";

type LogoProps = {
  size?: number;
  /** 어두운 배경 위: 흰 사각형 + 초록 선 */
  inverted?: boolean;
  className?: string;
  label?: string;
};

// 크기별 선 두께 (DESIGN.md 1. 브랜드)
function strokeFor(size: number) {
  if (size >= 64) return 3.2;
  if (size >= 48) return 3.6;
  if (size >= 30) return 3.8;
  if (size > 16) return 4.2;
  return 5;
}

export function Logo({ size = 30, inverted = false, className, label }: LogoProps) {
  const fill = inverted ? "var(--color-white)" : "var(--color-brand)";
  const stroke = inverted ? "var(--color-brand)" : "var(--color-white)";
  const strokeWidth = strokeFor(size);
  const isFavicon = size <= 16;
  const line = {
    fill: "none",
    stroke,
    strokeWidth,
    strokeLinecap: "round",
    strokeLinejoin: "round",
  } as const;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      className={className}
      {...(label ? { role: "img", "aria-label": label } : { "aria-hidden": true })}
    >
      <rect width="48" height="48" rx={isFavicon ? 12 : 14} fill={fill} />
      <path d="M12 22.5 24 12.5l12 10" {...line} />
      <path d="M15.5 20.5V33a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2V20.5" {...line} />
      {!isFavicon && <path d="m19.5 27 3.2 3.2 6-6.2" {...line} />}
    </svg>
  );
}

export function Logotype({ className }: { className?: string }) {
  return <span className={cn("tracking-logo font-extrabold", className)}>무주택자들</span>;
}
