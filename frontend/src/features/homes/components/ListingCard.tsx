import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { CardFavoriteHeart } from "@/features/favorites/components/FavoriteButtons";
import type { HomeListing } from "@/features/homes/mocks/homes";
import { routes } from "@/shared/lib/routes";
import { cn } from "@/shared/lib/cn";
import { RankChip, VerdictBadge } from "@/shared/ui/Badge";

export function ListingCard({
  item,
  regionLabel,
  onLike,
}: {
  item: HomeListing;
  regionLabel: string;
  onLike: () => void;
}) {
  return (
    <article className="relative min-w-0 rounded-[16px] bg-white">
      <Link
        href={routes.notice(item.id)}
        className="text-text hover:text-brand-strong flex min-w-0 flex-col gap-2 rounded-[16px] px-4 py-3 no-underline sm:px-5 sm:py-4"
      >
        <div className="text-text-sub flex flex-wrap items-center gap-1.5 pr-10 text-[12px]">
          <span className="bg-fill rounded-full px-2 py-1">
            {[item.org, regionLabel].filter(Boolean).join(" · ")}
          </span>
          {item.due && (
            <span
              className={cn(
                "text-brand-strong rounded-full px-2 py-1 tabular-nums",
                /^D-\d/.test(item.due) && "bg-brand-soft font-bold",
              )}
            >
              {item.due}
            </span>
          )}
        </div>
        <h3 className="m-0 pr-10 text-[17px] leading-[1.45] font-bold break-words sm:text-[18px]">
          {item.title}
        </h3>
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <VerdictBadge verdict={item.verdict} size="xs" />
            {item.rank && <RankChip rank={item.rank} size="xs" />}
          </div>
          <span className="text-brand-strong ml-auto flex items-center gap-1.5 text-right text-[13px] font-semibold">
            {item.prepAmount ? (
              <>
                <span className="text-text-sub font-normal">예상 준비금</span>
                <strong className="text-[17px] font-bold tabular-nums">{item.prepAmount}</strong>
              </>
            ) : (
              item.prepNote
            )}
            <ChevronRight size={16} className="shrink-0" aria-hidden />
          </span>
        </div>
      </Link>
      <CardFavoriteHeart
        type="NOTICE"
        id={item.id}
        onAdd={onLike}
        className="absolute top-3 right-3 size-[44px]"
      />
    </article>
  );
}
