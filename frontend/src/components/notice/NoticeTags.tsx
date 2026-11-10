import { RankChip, VerdictBadge, type ListingVerdict } from "@/components/ui/Badge";
import { cn } from "@/lib/cn";

type NoticeTagsProps = {
  verdict: ListingVerdict;
  rank?: number;
  /** "마감 D-12" · "상시 모집" · "접수 예정" */
  due: string;
  tags: string[];
  /** PC는 5px 10px, 모바일은 4px 9px */
  size: "lg" | "md";
};

/** 공고 상세 맨 위: 판정 배지 · 순위 칩 · 마감 · 정보 태그 */
export function NoticeTags({ verdict, rank, due, tags, size }: NoticeTagsProps) {
  const pad = size === "lg" ? "px-[10px] py-[5px]" : "px-[9px] py-[4px]";
  return (
    <div className="flex flex-wrap gap-[6px]">
      <VerdictBadge verdict={verdict} size={size} />
      {rank !== undefined && <RankChip rank={rank} size={size} />}
      <span className={cn("rounded-badge bg-text text-[13px] font-bold text-white", pad)}>
        {due}
      </span>
      {tags.map((t) => (
        <span
          key={t}
          className={cn("rounded-badge bg-fill text-text-sub text-[13px] font-semibold", pad)}
        >
          {t}
        </span>
      ))}
    </div>
  );
}
