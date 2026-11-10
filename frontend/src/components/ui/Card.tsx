import { cn } from "@/lib/cn";

/** 카드: 흰 바탕, 그림자 없이 회색 페이지 위에 */
export function Card({ className, ...props }: React.HTMLAttributes<HTMLElement>) {
  return <section className={cn("rounded-card bg-surface", className)} {...props} />;
}
