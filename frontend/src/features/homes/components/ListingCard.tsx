import Link from "next/link";
import { CalendarDays, ChevronRight } from "lucide-react";
import { CardFavoriteHeart } from "@/features/favorites/components/FavoriteButtons";
import type { HomeListing } from "@/features/homes/mocks/homes";
import { routes } from "@/shared/lib/routes";
import { RankChip, VerdictBadge } from "@/shared/ui/Badge";
import { InfoTag } from "@/shared/ui/Chip";

export function ListingCard({
  item,
  regionLabel,
  onLike,
}: {
  item: HomeListing;
  regionLabel: string;
  onLike: () => void;
}) {
  const due = item.dueLong ?? item.due;
  return (
    <article className="rounded-card border-line-soft bg-surface relative flex min-w-0 flex-col border">
      <Link
        href={routes.notice(item.id)}
        className="rounded-card text-text hover:text-brand-strong flex min-w-0 flex-1 flex-col gap-[8px] p-[15px] no-underline lg:p-[18px]"
      >
        <div className="flex min-h-[30px] flex-wrap items-center gap-[5px] pr-[45px]">
          <VerdictBadge verdict={item.verdict} size="xs" />
          {item.rank && <RankChip rank={item.rank} size="xs" />}
        </div>
        <p className="text-text-sub text-[13px]">
          {[item.org, regionLabel].filter(Boolean).join(" · ")}
        </p>
        <h2 className="tracking-title m-0 text-[17px] leading-[1.4] font-extrabold break-words lg:text-[19px]">
          {item.title}
        </h2>
        {item.price && <p className="text-text text-[14px] font-semibold">{item.price}</p>}
        {(item.life || item.tags.length > 0) && (
          <div className="flex flex-wrap gap-[4px]">
            {item.life && <InfoTag>{item.life}</InfoTag>}
            {item.tags.map((tag) => (
              <InfoTag key={tag}>{tag}</InfoTag>
            ))}
          </div>
        )}
        <div className="border-line-soft text-text-sub mt-auto flex flex-wrap items-center gap-x-[12px] gap-y-[6px] border-t pt-[10px] text-[13px]">
          {due && (
            <span className="rounded-badge bg-fill text-text inline-flex items-center gap-[5px] px-[8px] py-[4px] font-bold">
              <CalendarDays size={14} aria-hidden /> {due}
            </span>
          )}
          <span className="min-w-0 flex-1">
            {item.prepAmount ? (
              <>
                예상 준비금 <strong className="text-text">{item.prepAmount}</strong>
              </>
            ) : (
              item.prepNote
            )}
          </span>
          <ChevronRight size={16} className="text-text-tertiary ml-auto shrink-0" aria-hidden />
        </div>
      </Link>
      <CardFavoriteHeart
        type="NOTICE"
        id={item.id}
        onAdd={onLike}
        className="absolute top-[8px] right-[8px] size-[44px]"
      />
    </article>
  );
}
