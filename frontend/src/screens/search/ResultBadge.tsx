import { cn } from "@/lib/cn";
import { Badge, VerdictBadge } from "@/components/ui/Badge";
import type { SearchBadge } from "@/mocks/search";

/** 검색 결과 오른쪽 배지: 판정 / 지원 불가 / 생활권 점수 */
export function ResultBadge({
  badge,
  size,
  className,
}: {
  badge: SearchBadge;
  size: "sm" | "lg";
  className?: string;
}) {
  const cls = cn("flex-none", className);
  if (badge.kind === "ok" || badge.kind === "check")
    return <VerdictBadge verdict={badge.kind} size={size} className={cls} />;
  if (badge.kind === "none")
    return (
      <Badge tone="neutral" size={size} className={cls}>
        지원 불가
      </Badge>
    );
  return (
    <Badge tone="neutral" size={size} className={cn(cls, "text-text")}>
      {badge.score}점
    </Badge>
  );
}
