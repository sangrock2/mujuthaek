"use client";

import { useState } from "react";
import { MFavoriteHeart } from "@/components/favorites/FavoriteButtons";
import { MBackHeader, MBottomActions } from "@/components/layout/MBackHeader";
import { MPage } from "@/components/layout/Responsive";
import { MNoticeChatButton, NoticeChat } from "@/components/chat/NoticeChat";
import { NoticeSections, NoticeToc } from "@/components/notice/NoticeSections";
import { NoticeTags } from "@/components/notice/NoticeTags";
import { PdfViewer } from "@/components/notice/PdfViewer";
import { MRankCard } from "@/components/notice/RankCard";
import { pdfSections, dueText } from "@/features/notice/format";
import { noticeParams, useJudgmentViewed } from "@/features/notice/analytics";
import { useNotice } from "@/features/notice/queries";
import { usePdfViewer } from "@/features/notice/usePdfViewer";
import { track } from "@/lib/analytics";
import { unitStatus, useUnitPicker } from "@/features/notice/useUnitPicker";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import type { NoticeUnit } from "@/mocks/notice";

const MOBILE_UNIT_COUNT = 6;

const card = "rounded-card bg-surface mx-[16px] flex flex-col";

const pos = (u: NoticeUnit) => {
  const p = u.mobilePos ?? u;
  return { left: `${p.x}%`, top: `${p.y}%` };
};

export function MDetailUnits({ id }: { id: string }) {
  const { data: n } = useNotice(id);
  // 개수·신청 가능 수는 전체로 세고, 목록만 처음 몇 집을 보여줘요
  const units = n?.kind === "units" ? n.units : [];
  const { onlyOk, setOnlyOk, shown, selected, select, countAll, countOk } = useUnitPicker(units);
  const [all, setAll] = useState(false);
  const pdf = usePdfViewer();
  useJudgmentViewed(id, n);
  if (n?.kind !== "units") return null;
  const { doc } = n;
  const pdfUrl = doc.source.pdfUrl;
  /** 원문 PDF가 있으면 시트로 열고, 없으면 기관 사이트로 */
  const openOriginal = (page = 1, label?: string) => {
    track("notice_source_open", { ...noticeParams(n), via: pdfUrl ? "pdf" : "site" });
    if (pdfUrl) pdf.show(page, label);
    else window.open(doc.source.detailUrl, "_blank", "noreferrer");
  };

  const seg = (on: boolean) =>
    cn(
      "min-h-[36px] cursor-pointer rounded-badge border-0 px-[10px] text-[13px] font-bold",
      on ? "bg-surface text-text" : "text-text-sub bg-transparent",
    );

  return (
    <MPage>
      <MBackHeader title="공고 상세" backHref={routes.homes} />
      <main className="flex flex-1 flex-col gap-[12px] pb-[24px]">
        <section className="bg-surface flex flex-col gap-[10px] p-[20px]">
          <NoticeTags
            verdict={n.verdict}
            rank={n.ranking?.myRank}
            due={dueText(n)}
            tags={n.tags}
            size="md"
          />
          <h2 className="tracking-h1 m-0 text-[23px] leading-[1.35] font-extrabold">{n.title}</h2>
          <span className="text-text-sub text-[14px] leading-[1.5]">{n.meta}</span>
        </section>

        <section aria-labelledby="u-h" className={cn(card, "gap-[12px] p-[16px]")}>
          <div className="flex items-center justify-between gap-[8px]">
            <h3 id="u-h" className="m-0 text-[17px] font-extrabold">
              공급 주택 {countAll}곳
            </h3>
            <div role="group" aria-label="보기" className="bg-fill flex rounded-[10px] p-[3px]">
              <button
                type="button"
                aria-pressed={!onlyOk}
                onClick={() => setOnlyOk(false)}
                className={seg(!onlyOk)}
              >
                전체
              </button>
              <button
                type="button"
                aria-pressed={onlyOk}
                onClick={() => setOnlyOk(true)}
                className={seg(onlyOk)}
              >
                신청 가능 {countOk}
              </button>
            </div>
          </div>
          <div
            role="img"
            aria-label={selected ? `지도 · 선택한 집 ${selected.name}` : "지도"}
            className="bg-placeholder-bg relative h-[220px] overflow-hidden rounded-[18px]"
          >
            <span
              aria-hidden
              className="bg-map-water absolute top-[120px] left-[-20px] h-[20px] w-[420px] -rotate-10"
            />
            <span
              aria-hidden
              className="bg-map-park-2 rounded-tile absolute top-[20px] left-[230px] h-[60px] w-[80px]"
            />
            {shown
              .filter((u) => u.id !== selected?.id)
              .map((u) => (
                <span
                  key={u.id}
                  className={cn(
                    "rounded-pill absolute box-content size-[14px] -translate-x-1/2 -translate-y-1/2 border-2 border-solid border-white",
                    u.ok ? "bg-brand" : "bg-placeholder-icon",
                  )}
                  style={pos(u)}
                />
              ))}
            {selected && (
              <span
                className="bg-text absolute -translate-x-1/2 -translate-y-full rounded-[10px] px-[9px] py-[5px] text-[12px] font-extrabold whitespace-nowrap text-white"
                style={pos(selected)}
              >
                {selected.short ?? selected.name}
              </span>
            )}
          </div>
          <div className="flex flex-col gap-[8px]">
            {(all ? shown : shown.slice(0, MOBILE_UNIT_COUNT)).map((u) => {
              const on = u.id === selected?.id;
              return (
                <button
                  key={u.id}
                  type="button"
                  aria-pressed={on}
                  onClick={() => select(u.id)}
                  className={cn(
                    "text-text rounded-tile flex cursor-pointer flex-col gap-[4px] border-2 border-solid px-[14px] py-[12px] text-left",
                    on ? "bg-row-selected border-brand" : "bg-surface border-line-soft",
                  )}
                >
                  <span className="flex w-full justify-between gap-[8px]">
                    <span className="text-[15px] font-extrabold">{u.name}</span>
                    <span
                      className={cn(
                        "rounded-tag flex-none px-[7px] py-[2px] text-[12px] font-bold",
                        u.ok ? "bg-ok-bg text-ok-text" : "bg-fill text-text-sub",
                      )}
                    >
                      {unitStatus(u)}
                    </span>
                  </span>
                  <span className="text-text-sub text-[13px]">
                    {u.type} · {u.area} · {u.floor} · {u.stationShort ?? u.station}
                  </span>
                  <span className="text-[14px] font-bold">
                    보증금 {u.deposit} · {u.rent}
                  </span>
                </button>
              );
            })}
            {!all && shown.length > MOBILE_UNIT_COUNT && (
              <button
                type="button"
                onClick={() => setAll(true)}
                className="bg-fill text-text min-h-[44px] cursor-pointer rounded-sm border-0 text-[14px] font-bold"
              >
                {shown.length - MOBILE_UNIT_COUNT}곳 더 보기
              </button>
            )}
          </div>
          <button
            type="button"
            className="text-brand inline-flex min-h-[44px] cursor-pointer items-center self-start border-0 bg-transparent p-0 text-[14px] font-bold"
          >
            원본 엑셀 내려받기
          </button>
        </section>

        <section aria-labelledby="el-h" className={cn(card, "px-[20px] pt-[16px] pb-[6px]")}>
          <h3 id="el-h" className="mx-0 mt-0 mb-[6px] text-[17px] font-extrabold">
            내 자격
          </h3>
          {n.eligibility.map((e, i) => (
            <div
              key={e.label}
              className={cn(
                "flex justify-between py-[11px] text-[15px]",
                i < n.eligibility.length - 1 && "border-line-soft border-b border-solid",
              )}
            >
              <span>{e.shortLabel}</span>
              <span
                className={cn(
                  "font-bold",
                  e.status === "met" ? "text-brand-strong" : "text-check-text",
                )}
              >
                {e.status === "met" ? "충족" : "확인 필요"}
              </span>
            </div>
          ))}
        </section>

        {n.ranking && <MRankCard ranking={n.ranking} />}

        <NoticeToc doc={doc} variant="mobile" />
        <NoticeSections doc={doc} variant="mobile" onOpenPage={pdfUrl ? openOriginal : undefined} />

        <NoticeChat noticeId={n.id} variant="mobile" />
      </main>
      <MBottomActions>
        <MFavoriteHeart
          type="NOTICE"
          id={n.id}
          onAdd={() => track("notice_bookmark", noticeParams(n))}
        />
        <MNoticeChatButton noticeId={n.id} />
        <div className="flex min-w-0 flex-1 flex-col gap-[6px]">
          {selected && (
            <span className="text-text-sub text-center text-[13px]">
              {selected.name} · 준비할 돈 {selected.prep}
            </span>
          )}
          <button
            type="button"
            onClick={() => openOriginal()}
            className="rounded-control bg-brand flex min-h-[56px] cursor-pointer items-center justify-center border-0 text-[17px] font-extrabold text-white"
          >
            {n.agency} 공고 원문 보기
          </button>
        </div>
      </MBottomActions>
      {pdfUrl && (
        <PdfViewer
          open={pdf.open}
          onClose={pdf.close}
          src={pdfUrl}
          fileName={doc.source.fileName}
          detailUrl={doc.source.detailUrl}
          target={pdf.target}
          sections={pdfSections(doc)}
          onJump={pdf.show}
          variant="mobile"
        />
      )}
    </MPage>
  );
}
