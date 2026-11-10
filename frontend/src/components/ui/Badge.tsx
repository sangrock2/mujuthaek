import { cn } from "@/lib/cn";

const tones = {
  ok: "bg-ok-bg text-ok-text",
  check: "bg-check-bg text-check-text",
  neutral: "bg-neutral-bg text-neutral-text",
  rank: "bg-rank-bg text-rank-text",
  danger: "bg-danger-bg text-danger-text", // 관리자 전용
} as const;

const sizes = {
  xs: "rounded-tag px-[7px] py-[2px] text-[12px]",
  sm: "rounded-badge px-[8px] py-[3px] text-[12px]",
  md: "rounded-badge px-[9px] py-[4px] text-[13px]",
  lg: "rounded-badge px-[10px] py-[5px] text-[13px]",
} as const;

export type BadgeTone = keyof typeof tones;

type BadgeProps = {
  tone: BadgeTone;
  size?: keyof typeof sizes;
  className?: string;
  children: React.ReactNode;
};

export function Badge({ tone, size = "lg", className, children }: BadgeProps) {
  return <span className={cn("font-bold", tones[tone], sizes[size], className)}>{children}</span>;
}

/** 판정 배지는 두 가지: 지원 가능 / 확인 필요 */
export type Verdict = "ok" | "check";

/** 공고 목록은 '지원 불가까지 보기'를 켜면 지원 불가도 보여요 */
export type ListingVerdict = Verdict | "no";

export const verdictLabel: Record<ListingVerdict, string> = {
  ok: "지원 가능",
  check: "확인 필요",
  no: "지원 불가",
};

const verdictTone: Record<ListingVerdict, BadgeTone> = { ok: "ok", check: "check", no: "neutral" };

export function VerdictBadge({
  verdict,
  ...rest
}: { verdict: ListingVerdict } & Omit<BadgeProps, "tone" | "children">) {
  return (
    <Badge tone={verdictTone[verdict]} {...rest}>
      {verdictLabel[verdict]}
    </Badge>
  );
}

/** 순위가 있는 공고에서만 판정 배지 오른쪽에 둬요 */
export function RankChip({
  rank,
  ...rest
}: { rank: number } & Omit<BadgeProps, "tone" | "children">) {
  return (
    <Badge tone="rank" {...rest}>
      {rank}순위
    </Badge>
  );
}
