"use client";

import { ChevronDown, CircleAlert, ExternalLink, FileText, MapPin, Phone } from "lucide-react";
import {
  categoryLabel,
  channelLabel,
  documentGroupLabel,
  formatPeriod,
  formatWon,
  formatWonRange,
  sectionTitles,
  selectionLabel,
  visibleSections,
} from "@/features/notice/format";
import { cn } from "@/lib/cn";
import type {
  EligibilityCategory,
  NoticeDoc,
  NoticeHousingType,
  NoticeSectionKey,
  NoticeSelectionKind,
} from "@/mocks/notice-doc";

type Variant = "web" | "mobile";

type SectionsProps = {
  doc: NoticeDoc;
  variant: Variant;
  /** 원문 PDF가 있을 때만: 해당 쪽 열기 */
  onOpenPage?: (page: number, label: string) => void;
};

type FoldItem = { id: string; text: string; detail?: string };

/**
 * 분류별로 접어 둔 목록 (누가 신청할 수 있나요 · 어떻게 뽑나요). 분류마다 배지 하나에 첫 항목을 한 줄로 미리 보여주고, 누르면 항목이 한 칸씩 펼쳐져요
 */
function FoldGroups({
  groups,
  badge,
  web,
}: {
  groups: { key: string; label: string; items: FoldItem[] }[];
  /** 배지 색 */
  badge: string;
  web: boolean;
}) {
  const shown = groups.filter((g) => g.items.length);
  const sub = web ? "text-[15px]" : "text-[14px]";
  return (
    <ul className="m-0 flex list-none flex-col p-0">
      {shown.map((g, i) => (
        <li
          key={g.key}
          className={cn(i < shown.length - 1 && "border-line-soft border-b border-solid")}
        >
          <details className="group">
            <summary className="flex min-h-[48px] cursor-pointer list-none items-center gap-[12px] py-[10px] [&::-webkit-details-marker]:hidden">
              <span
                className={cn(
                  "rounded-tag flex-none px-[8px] py-[3px] text-center text-[12px] font-bold",
                  web ? "min-w-[56px]" : "min-w-[48px]",
                  badge,
                )}
              >
                {g.label}
              </span>
              <span className={cn(sub, "min-w-0 flex-1 truncate group-open:invisible")}>
                {g.items[0].text}
              </span>
              {g.items.length > 1 && (
                <span className="text-text-sub flex-none text-[13px] font-semibold">
                  {g.items.length}개
                </span>
              )}
              <ChevronDown
                size={18}
                aria-hidden
                className="text-text-sub flex-none transition-transform group-open:rotate-180"
              />
            </summary>
            <ul className="m-0 flex list-none flex-col gap-[6px] p-0 pb-[12px]">
              {g.items.map((e) => (
                <li
                  key={e.id}
                  className="bg-bg rounded-tile flex flex-col gap-[4px] px-[14px] py-[10px]"
                >
                  <span className={cn(sub, "leading-[1.5]")}>{e.text}</span>
                  {e.detail && (
                    <span className="text-text-sub text-[13px] leading-[1.5]">
                      예외 · {e.detail}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </details>
        </li>
      ))}
    </ul>
  );
}

/** 가격 대상이 둘 이상일 때만 「가격 대상」 칸을 둬요 */
const hasTarget = (types: NoticeHousingType[]) => new Set(types.map((t) => t.target)).size > 1;

export const sectionId = (k: NoticeSectionKey) => `notice-${k}`;

/** 목차: 누르면 해당 섹션으로 내려가요 */
export function NoticeToc({ doc, variant }: { doc: NoticeDoc; variant: Variant }) {
  const keys = visibleSections(doc);
  const web = variant === "web";
  return (
    <nav
      aria-label="공고 목차"
      className={cn(
        "bg-bg sticky z-[1] flex gap-[6px] overflow-x-auto",
        // 상단 바(웹 69px·모바일 56px) 바로 아래에 붙어요
        web ? "top-[69px] -mx-[4px] px-[4px] py-[10px]" : "top-[56px] px-[16px] py-[8px]",
      )}
    >
      {keys.map((k) => (
        <a
          key={k}
          href={`#${sectionId(k)}`}
          className={cn(
            "rounded-pill bg-surface text-text-sub hover:text-text inline-flex flex-none items-center font-bold whitespace-nowrap no-underline",
            web ? "min-h-[40px] px-[16px] text-[14px]" : "min-h-[36px] px-[14px] text-[13px]",
          )}
        >
          {sectionTitles[k].toc}
        </a>
      ))}
    </nav>
  );
}

/** 공고 원문을 목차별로 정리한 섹션들 */
export function NoticeSections({ doc, variant, onOpenPage }: SectionsProps) {
  const web = variant === "web";
  const keys = visibleSections(doc);
  const card = web
    ? "rounded-card-lg bg-surface flex flex-col gap-[16px] px-[30px] py-[28px]"
    : "rounded-card bg-surface mx-[16px] flex flex-col gap-[12px] px-[20px] py-[18px]";
  const sub = web ? "text-[15px]" : "text-[14px]";

  const header = (k: NoticeSectionKey) => {
    const page = doc.pages[k];
    const { heading } = sectionTitles[k];
    return (
      <div className="flex items-center justify-between gap-[10px]">
        <h2
          className={cn("tracking-title m-0 font-extrabold", web ? "text-[21px]" : "text-[17px]")}
        >
          {heading}
        </h2>
        {page && onOpenPage && (
          <button
            type="button"
            onClick={() => onOpenPage(page, sectionTitles[k].toc)}
            className="text-brand-strong inline-flex min-h-[40px] flex-none cursor-pointer items-center gap-[4px] border-0 bg-transparent p-0 text-[13px] font-bold"
          >
            <FileText size={15} aria-hidden />
            원문 p.{page}
          </button>
        )}
      </div>
    );
  };

  const body: Record<NoticeSectionKey, () => React.ReactNode> = {
    eligibility: () => (
      <FoldGroups
        web={web}
        badge="bg-fill text-text-sub"
        groups={(Object.keys(categoryLabel) as EligibilityCategory[]).map((category) => ({
          key: category,
          label: categoryLabel[category],
          items: doc.eligibility.filter((e) => e.category === category),
        }))}
      />
    ),

    housing: () => (
      <div className="flex flex-col gap-[16px]">
        {doc.housing.map((h) => (
          <div key={h.id} className="flex flex-col gap-[10px]">
            <div className="flex flex-col gap-[2px]">
              <span className={cn("font-extrabold", web ? "text-[17px]" : "text-[16px]")}>
                {h.complexName}
              </span>
              <span className="text-text-sub inline-flex items-center gap-[4px] text-[13px]">
                <MapPin size={14} aria-hidden />
                {h.address}
              </span>
            </div>
            {web ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[520px] border-collapse text-[15px]">
                  <thead>
                    <tr className="text-text-sub text-left text-[13px]">
                      {[
                        "주택형",
                        "전용면적",
                        ...(hasTarget(h.types) ? ["가격 대상"] : []),
                        "모집",
                        "보증금",
                        "월 임대료",
                      ].map((t, i, all) => (
                        <th
                          key={t}
                          className={cn(
                            "border-line border-b border-solid px-[12px] py-[10px] font-semibold",
                            i >= all.length - 3 && "text-right",
                          )}
                        >
                          {t}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {h.types.map((t, i) => {
                      const td = cn("px-[12px] py-[14px]", t.mine && "font-bold");
                      return (
                        <tr key={`${t.code}-${i}`} className={cn(t.mine && "bg-brand-soft")}>
                          <td className={cn(td, "font-bold", t.mine && "rounded-l-[12px]")}>
                            {t.code}
                          </td>
                          <td className={td}>{t.areaSqm === null ? "–" : `${t.areaSqm}㎡`}</td>
                          {hasTarget(h.types) && <td className={td}>{t.target ?? "–"}</td>}
                          <td className={cn(td, "text-right")}>
                            {t.offered === null ? "–" : `${t.offered}호`}
                          </td>
                          <td className={cn(td, "text-right")}>
                            {formatWonRange(t.depositWon, t.depositMaxWon)}
                          </td>
                          <td className={cn(td, "text-right", t.mine && "rounded-r-[12px]")}>
                            {formatWonRange(t.monthlyRentWon, t.monthlyRentMaxWon)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              h.types.map((t, i) => (
                <div
                  key={`${t.code}-${i}`}
                  className={cn(
                    "rounded-tile flex items-center justify-between gap-[10px] p-[14px]",
                    t.mine ? "bg-brand-soft" : "bg-bg",
                  )}
                >
                  <span className="flex flex-col gap-[2px]">
                    <span className="text-[16px] font-extrabold">
                      {t.code}
                      {t.areaSqm !== null && ` · ${t.areaSqm}㎡`}
                    </span>
                    <span
                      className={cn("text-[13px]", t.mine ? "text-brand-strong" : "text-text-sub")}
                    >
                      {[
                        hasTarget(h.types) && t.target,
                        t.offered !== null && `${t.offered}호`,
                        t.mine && "신청 가능",
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </span>
                  <span className="text-right text-[14px] font-bold">
                    {formatWonRange(t.depositWon, t.depositMaxWon)}
                    <br />월 {formatWonRange(t.monthlyRentWon, t.monthlyRentMaxWon)}
                  </span>
                </div>
              ))
            )}
            {h.types
              .filter((t) => t.contractWon && t.balanceWon)
              .map((t, i) => (
                <span key={`${t.code}-${i}`} className="text-text-sub text-[13px]">
                  {h.types.length > 1 && `${t.code} · `}보증금 = 계약금 {formatWon(t.contractWon!)}{" "}
                  + 잔금 {formatWon(t.balanceWon!)}
                </span>
              ))}
            {(h.basis || h.types.some((t) => t.mine)) && (
              <span className="text-text-sub text-[13px]">
                {[
                  h.basis,
                  h.types.some((t) => t.mine) && "초록색은 내 조건으로 신청할 수 있는 주택형이에요",
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            )}
          </div>
        ))}
      </div>
    ),

    schedule: () => (
      <ol className="m-0 flex list-none flex-col p-0">
        {doc.schedule.map((s, i) => {
          const period = formatPeriod(s.start, s.end);
          const last = i === doc.schedule.length - 1;
          return (
            <li key={s.id} className="relative flex gap-[14px] pb-[16px] last:pb-0">
              {!last && (
                <span
                  aria-hidden
                  className="bg-line absolute top-[16px] bottom-0 left-[4px] w-[2px]"
                />
              )}
              <span
                aria-hidden
                className={cn(
                  "rounded-pill relative mt-[6px] size-[10px] flex-none",
                  s.state === "done" && "bg-off",
                  s.state === "now" && "bg-brand shadow-[0_0_0_4px_var(--color-brand-soft)]",
                  s.state === "todo" && "bg-check-off",
                )}
              />
              <span className="flex min-w-0 flex-col gap-[3px]">
                <span
                  className={cn(
                    sub,
                    "font-bold",
                    s.state === "done" && "text-text-sub font-semibold",
                  )}
                >
                  {s.label}
                  {s.state === "now" && <span className="text-brand-strong"> · 진행 중</span>}
                </span>
                <span className={cn(sub, s.state === "done" && "text-text-sub")}>
                  {period ?? "날짜 미정"}
                </span>
                {s.time && <span className="text-text-sub text-[13px]">{s.time}</span>}
                {s.note && <span className="text-text-sub text-[13px]">{s.note}</span>}
              </span>
            </li>
          );
        })}
      </ol>
    ),

    apply: () => {
      const { apply } = doc;
      const rows = [
        apply.channel && { label: "방법", value: channelLabel[apply.channel] },
        apply.place && { label: "장소", value: `${apply.place.name} · ${apply.place.address}` },
        apply.hours && { label: "시간", value: apply.hours },
      ].filter(Boolean) as { label: string; value: string }[];
      return (
        <div className="flex flex-col gap-[14px]">
          {apply.method && <p className={cn(sub, "m-0 leading-[1.6]")}>{apply.method}</p>}
          {rows.length > 0 && (
            <dl className="bg-bg rounded-tile m-0 flex flex-col gap-[8px] px-[16px] py-[14px]">
              {rows.map((r) => (
                <div key={r.label} className="flex gap-[12px] text-[14px]">
                  <dt className="text-text-sub w-[32px] flex-none">{r.label}</dt>
                  <dd className="m-0 font-semibold">{r.value}</dd>
                </div>
              ))}
            </dl>
          )}
          {apply.url && (
            <a
              href={apply.url}
              target="_blank"
              rel="noreferrer"
              className="rounded-control bg-brand inline-flex min-h-[48px] items-center justify-center gap-[6px] self-start px-[18px] text-[15px] font-bold text-white no-underline hover:text-white"
            >
              <ExternalLink size={17} aria-hidden />
              신청 사이트 열기
            </a>
          )}
          {apply.documents.length > 0 && (
            <div className="flex flex-col gap-[8px]">
              <span className={cn("font-extrabold", web ? "text-[17px]" : "text-[15px]")}>
                준비할 서류
              </span>
              {apply.documents.map((g) => (
                <details
                  key={g.group}
                  open={g.group === "COMMON"}
                  className="rounded-tile border-line-soft border border-solid"
                >
                  <summary className="flex min-h-[48px] cursor-pointer items-center justify-between gap-[8px] px-[16px] text-[15px] font-bold">
                    {documentGroupLabel[g.group]}
                    <span className="text-text-sub text-[13px] font-semibold">
                      {g.items.length}개
                    </span>
                  </summary>
                  <ul className="m-0 flex list-none flex-col gap-[12px] px-[16px] pt-[4px] pb-[16px]">
                    {g.items.map((d) => (
                      <li key={d.id} className="flex flex-col gap-[2px]">
                        <span className="text-[15px] font-bold">{d.name}</span>
                        {d.when && (
                          <span className="text-brand-strong text-[13px] font-semibold">
                            {d.when}
                          </span>
                        )}
                        <span className="text-text-sub text-[13px] leading-[1.5]">{d.desc}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              ))}
            </div>
          )}
        </div>
      );
    },

    selection: () => (
      <FoldGroups
        web={web}
        badge="bg-rank-bg text-rank-text"
        groups={(Object.keys(selectionLabel) as NoticeSelectionKind[]).map((kind) => ({
          key: kind,
          label: selectionLabel[kind],
          items: doc.selection.filter((r) => r.kind === kind),
        }))}
      />
    ),

    cautions: () => (
      <ul className="m-0 flex list-none flex-col gap-[8px] p-0">
        {doc.cautions.map((c) => (
          <li key={c.id} className="bg-check-bg rounded-tile flex gap-[10px] px-[16px] py-[14px]">
            <CircleAlert size={18} className="text-check-text mt-[2px] flex-none" aria-hidden />
            <span className="flex flex-col gap-[3px]">
              <span className="text-check-text text-[15px] font-bold">{c.title}</span>
              <span className="text-text text-[14px] leading-[1.5]">{c.text}</span>
            </span>
          </li>
        ))}
      </ul>
    ),

    living: () => (
      <ul className="m-0 flex list-none flex-col p-0">
        {doc.living.map((l, i) => (
          <li
            key={l.id}
            className={cn(
              "flex flex-col gap-[3px] py-[12px]",
              i < doc.living.length - 1 && "border-line-soft border-b border-solid",
            )}
          >
            <span className="text-[15px] font-bold">{l.title}</span>
            <span className="text-text-sub text-[14px] leading-[1.5]">{l.text}</span>
          </li>
        ))}
      </ul>
    ),

    contacts: () => (
      <ul className="m-0 flex list-none flex-col gap-[8px] p-0">
        {doc.contacts.map((c) => (
          <li
            key={c.id}
            className="bg-bg rounded-tile flex items-center justify-between gap-[12px] px-[16px] py-[12px]"
          >
            <span className="flex min-w-0 flex-col gap-[2px]">
              <span className="text-[15px] font-bold">{c.name}</span>
              <span className="text-text-sub text-[13px]">{c.desc}</span>
            </span>
            {c.phone && (
              <a
                href={`tel:${c.phone}`}
                className="bg-surface text-text hover:text-text inline-flex min-h-[44px] flex-none items-center gap-[6px] rounded-sm px-[14px] text-[14px] font-bold no-underline"
              >
                <Phone size={16} aria-hidden />
                {c.phone}
              </a>
            )}
          </li>
        ))}
      </ul>
    ),
  };

  return (
    <>
      {keys.map((k) => (
        <section
          key={k}
          id={sectionId(k)}
          aria-label={sectionTitles[k].heading}
          className={cn(card, web ? "scroll-mt-[136px]" : "scroll-mt-[112px]")}
        >
          {header(k)}
          {body[k]()}
        </section>
      ))}
    </>
  );
}
