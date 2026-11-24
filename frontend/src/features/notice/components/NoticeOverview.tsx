import { ArrowRight, CalendarDays, FileText } from "lucide-react";
import { NoticeTags } from "@/features/notice/components/NoticeTags";
import { RegulationNotice } from "@/features/notice/components/RegulationNotice";
import { dueText, formatPeriod, statusLabel } from "@/features/notice/format";
import type { StandardNotice } from "@/features/notice/mocks/notice";
import type { ListingVerdict } from "@/shared/ui/Badge";
import { cn } from "@/shared/lib/cn";

export function NoticeOverview({
  notice,
  verdict,
  variant,
  onOpenPdf,
}: {
  notice: StandardNotice;
  verdict?: ListingVerdict;
  variant: "web" | "mobile";
  onOpenPdf?: () => void;
}) {
  const { doc, facts } = notice;
  const mobile = variant === "mobile";
  const deadline = doc.applyPeriod?.end;
  const factCount = facts.length + Number(Boolean(deadline));

  return (
    <section
      aria-label="공고 요약"
      className={cn(
        "rounded-card-lg border-line-soft bg-surface overflow-hidden border",
        mobile && "mx-3 mt-3",
      )}
    >
      <div className={cn("flex flex-col gap-4", mobile ? "p-5" : "px-8 pt-7 pb-6")}>
        <div className="flex flex-col gap-2.5">
          <p className="text-text-sub text-[13px] font-semibold md:text-[14px]">{notice.meta}</p>
          <NoticeTags
            verdict={verdict}
            rank={notice.ranking?.myRank}
            due={dueText(notice)}
            tags={notice.tags.filter((tag) => !notice.meta.includes(tag))}
            size={mobile ? "md" : "lg"}
          />
          <h1
            className={cn(
              "tracking-h1 m-0 leading-[1.25] font-extrabold break-keep",
              mobile ? "text-[25px]" : "text-[36px]",
            )}
          >
            {notice.title}
          </h1>
          {doc.summary && (
            <p className="text-text-sub m-0 max-w-[78ch] text-[15px] leading-relaxed">
              {doc.summary}
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <a
            href="#eligibility-h"
            className="rounded-control bg-brand hover:bg-brand-strong inline-flex min-h-[44px] items-center gap-1.5 px-4 text-[14px] font-bold text-white no-underline hover:text-white"
          >
            내 자격 보기
            <ArrowRight size={16} aria-hidden />
          </a>
          {onOpenPdf && (
            <button
              type="button"
              onClick={onOpenPdf}
              className="rounded-control border-line text-text hover:bg-fill inline-flex min-h-[44px] cursor-pointer items-center gap-1.5 border bg-transparent px-4 text-[14px] font-bold"
            >
              <FileText size={16} aria-hidden /> 공고 PDF 열기
            </button>
          )}
        </div>
        <RegulationNotice noticeId={notice.id} variant={variant} />
      </div>
      {factCount > 0 && (
        <dl
          className="border-line-soft bg-bg m-0 grid grid-cols-2 gap-px overflow-hidden border-t"
          style={
            mobile ? undefined : { gridTemplateColumns: `repeat(${factCount}, minmax(0, 1fr))` }
          }
        >
          {facts.map((fact) => (
            <div key={fact.label} className="bg-surface px-4 py-3 md:px-6 md:py-4">
              <dt className="text-text-sub text-[12px] font-semibold">{fact.label}</dt>
              <dd className="mx-0 mt-1 mb-0 text-[15px] leading-snug font-extrabold break-keep md:text-[17px]">
                {fact.value}
              </dd>
            </div>
          ))}
          {deadline && (
            <div className="bg-brand-soft px-4 py-3 md:px-6 md:py-4">
              <dt className="text-brand-strong flex items-center gap-1 text-[12px] font-bold">
                <CalendarDays size={13} aria-hidden /> 접수 마감
              </dt>
              <dd className="text-brand-strong mx-0 mt-1 mb-0 text-[15px] leading-snug font-extrabold md:text-[17px]">
                {formatPeriod(deadline, deadline)}
                {doc.applyPeriod?.endTime && ` ${doc.applyPeriod.endTime}`}
              </dd>
            </div>
          )}
        </dl>
      )}
      {doc.applyPeriod && (
        <div className="border-line-soft text-text-sub flex flex-wrap items-baseline gap-x-2 gap-y-1 border-t px-4 py-3 text-[13px] md:px-6">
          <span className="text-text font-bold">{statusLabel[doc.status]}</span>
          <span>접수 기간 {formatPeriod(doc.applyPeriod.start, doc.applyPeriod.end)}</span>
          {doc.applyPeriod.note && <span>{doc.applyPeriod.note}</span>}
        </div>
      )}
    </section>
  );
}
