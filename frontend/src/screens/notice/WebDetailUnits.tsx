"use client";

import { WebFavoriteButton } from "@/components/favorites/FavoriteButtons";
import Link from "next/link";
import { ArrowRight, ChevronRight, FileText, MapPin } from "lucide-react";
import { WebHeader } from "@/components/layout/WebHeader";
import { WebMain, WebPage } from "@/components/layout/Responsive";
import {
  DETAIL_MAIN_BASIS_WITH_CHAT,
  NoticeChat,
  WebNoticeChatButton,
  useNoticeChatOpen,
} from "@/components/chat/NoticeChat";
import { NoticeSections, NoticeToc } from "@/components/notice/NoticeSections";
import { NoticeTags } from "@/components/notice/NoticeTags";
import { PdfViewer } from "@/components/notice/PdfViewer";
import { WebRankCard } from "@/components/notice/RankCard";
import { WebUnitFilter } from "@/components/notice/UnitFilter";
import { pdfSections, dueText } from "@/features/notice/format";
import { noticeParams, useJudgmentViewed } from "@/features/notice/analytics";
import { useNotice } from "@/features/notice/queries";
import { track } from "@/lib/analytics";
import { usePdfViewer } from "@/features/notice/usePdfViewer";
import { unitStatus, useUnitPicker } from "@/features/notice/useUnitPicker";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";

const sectionTitle = "tracking-title m-0 text-[21px] font-extrabold";

/** 지도 그림 위 역 이름 */
const stations = [
  { label: "망원역", pos: "left-[25%] top-[64%]" },
  { label: "합정역", pos: "left-[42%] top-[76%]" },
  { label: "홍대입구역", pos: "left-[58%] top-[36%]" },
];

export function WebDetailUnits({ id }: { id: string }) {
  const { data: n } = useNotice(id);
  const units = n?.kind === "units" ? n.units : [];
  const { onlyOk, setOnlyOk, shown, selected, select, countAll, countOk } = useUnitPicker(units);
  const pdf = usePdfViewer();
  // 채팅 패널이 열린 동안은 본문 기본 폭을 줄여서 오른쪽 칸(관심 등록 · 이야기 닫기)이 본문 아래로 내려가지 않게 해요
  const chatOpen = useNoticeChatOpen(n?.id ?? id);
  useJudgmentViewed(id, n);
  if (n?.kind !== "units") return null;
  const { doc } = n;
  const pdfUrl = doc.source.pdfUrl;
  /** 원문 PDF가 있으면 옆에 열고, 없으면 기관 사이트로 */
  const openOriginal = (page = 1, label?: string) => {
    track("notice_source_open", { ...noticeParams(n), via: pdfUrl ? "pdf" : "site" });
    if (pdfUrl) pdf.show(page, label);
    else window.open(doc.source.detailUrl, "_blank", "noreferrer");
  };

  return (
    <WebPage>
      <div className={cn("flex flex-1 flex-col", pdf.open && pdfUrl && "pl-[min(46vw,680px)]")}>
        <WebHeader mode="home" current={routes.homes} />
        <WebMain className="gap-[16px] pt-[24px] pb-[80px]">
          <nav
            aria-label="위치"
            className="text-text-tertiary flex items-center gap-[4px] text-[14px]"
          >
            <Link
              href={routes.homes}
              className="text-text-sub hover:text-text-sub inline-flex min-h-[36px] items-center font-semibold no-underline"
            >
              내 집
            </Link>
            <ChevronRight size={16} aria-hidden />
            <span aria-current="page">{n.title}</span>
          </nav>

          <section
            aria-label="공고 요약"
            className="rounded-card-lg bg-surface flex flex-wrap items-end justify-between gap-[24px] px-[30px] py-[28px]"
          >
            <div className="flex flex-col gap-[10px]">
              <NoticeTags
                verdict={n.verdict}
                rank={n.ranking?.myRank}
                due={dueText(n)}
                tags={n.tags}
                size="lg"
              />
              <h1 className="tracking-h1 m-0 text-[34px] font-extrabold">{n.title}</h1>
              <span className="text-text-sub text-[16px]">{n.meta}</span>
            </div>
            <dl className="m-0 flex flex-wrap gap-[10px]">
              {n.facts.map((f) => (
                <div key={f.label} className="bg-bg rounded-tile min-w-[120px] px-[18px] py-[14px]">
                  <dt className="text-text-sub text-[13px]">{f.label}</dt>
                  <dd className="mx-0 mt-[4px] mb-0 text-[17px] font-bold">{f.value}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section
            aria-label="공급 주택 목록"
            className="rounded-card-lg bg-surface flex flex-col gap-[18px] px-[30px] pt-[26px] pb-[30px]"
          >
            <div className="flex flex-wrap items-center justify-between gap-[12px]">
              <div className="flex flex-col gap-[4px]">
                <h2 className={sectionTitle}>
                  공급 주택 목록 <span className="text-brand">{countAll}곳</span>
                </h2>
                <span className="text-text-sub text-[14px]">
                  공고에 붙은 주택목록 엑셀을 정리했어요. 집을 고르면 지도에서 위치를 보여드려요
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-[8px]">
                <WebUnitFilter
                  onlyOk={onlyOk}
                  setOnlyOk={setOnlyOk}
                  countAll={countAll}
                  countOk={countOk}
                  wide
                />
                <button
                  type="button"
                  className="text-text-sub inline-flex min-h-[44px] cursor-pointer items-center gap-[4px] border-0 bg-transparent px-[6px] text-[14px] font-bold"
                >
                  <FileText size={16} aria-hidden />
                  원본 엑셀
                </button>
              </div>
            </div>

            <div className="flex flex-wrap items-stretch gap-[20px]">
              <div
                role="group"
                aria-label="주택 목록"
                className="box-content flex max-h-[620px] min-w-0 flex-col gap-[8px] overflow-y-auto pr-[4px]"
                style={{ flex: "1 1 380px" }}
              >
                {shown.map((u) => {
                  const on = u.id === selected?.id;
                  return (
                    <button
                      key={u.id}
                      type="button"
                      aria-pressed={on}
                      onClick={() => select(u.id)}
                      className={cn(
                        "text-text flex cursor-pointer flex-col gap-[6px] rounded-[18px] border-2 border-solid px-[16px] py-[14px] text-left",
                        on ? "bg-row-selected border-brand" : "bg-surface border-line-soft",
                      )}
                    >
                      <span className="flex w-full items-center justify-between gap-[8px]">
                        <span className="text-[16px] font-bold">{u.name}</span>
                        <span
                          className={cn(
                            "rounded-badge flex-none px-[9px] py-[4px] text-[12px] font-bold",
                            u.ok ? "bg-ok-bg text-ok-text" : "bg-fill text-text-sub",
                          )}
                        >
                          {unitStatus(u)}
                        </span>
                      </span>
                      <span className="text-text-sub text-[13px]">
                        {u.type} · {u.area} · {u.floor} · {u.elevator}
                      </span>
                      <span className="flex w-full items-center justify-between gap-[8px]">
                        <span className="text-[15px] font-bold">
                          보증금 {u.deposit} · {u.rent}
                        </span>
                        <span className="text-text-sub text-[13px]">{u.station}</span>
                      </span>
                    </button>
                  );
                })}
              </div>

              <div className="flex min-w-0 flex-col gap-[12px]" style={{ flex: "999 1 460px" }}>
                <div
                  role="group"
                  aria-label="주택 위치 지도"
                  className="bg-map-road relative h-[440px] overflow-hidden rounded-[22px]"
                >
                  <span
                    aria-hidden
                    className="bg-map-water-2 absolute right-[-10%] bottom-[-6%] left-[-10%] h-[22%] -rotate-6"
                  />
                  <span
                    aria-hidden
                    className="bg-map-park absolute top-[52%] left-[66%] h-[22%] w-[18%] rounded-[40%_60%_55%_45%]"
                  />
                  <span
                    aria-hidden
                    className="absolute top-[33%] right-0 left-0 h-[10px] bg-white"
                  />
                  <span
                    aria-hidden
                    className="absolute top-[64%] right-0 left-0 h-[8px] -rotate-4 bg-white"
                  />
                  <span
                    aria-hidden
                    className="absolute top-0 bottom-0 left-[48%] w-[10px] rotate-8 bg-white"
                  />
                  <span
                    aria-hidden
                    className="absolute top-0 bottom-0 left-[27%] w-[7px] bg-white"
                  />
                  {stations.map((s) => (
                    <span
                      key={s.label}
                      aria-hidden
                      className={cn(
                        "rounded-tag text-text-sub absolute bg-white px-[6px] py-[2px] text-[12px] font-bold",
                        s.pos,
                      )}
                    >
                      {s.label}
                    </span>
                  ))}
                  <span
                    aria-hidden
                    className="text-brand-strong absolute top-[60%] left-[68%] text-[12px]"
                  >
                    공원
                  </span>

                  {shown
                    .filter((u) => u.id !== selected?.id)
                    .map((u) => (
                      <button
                        key={u.id}
                        type="button"
                        aria-label={`${u.name}, ${unitStatus(u)} 위치 보기`}
                        onClick={() => select(u.id)}
                        className="absolute mt-[-15px] ml-[-15px] flex size-[30px] cursor-pointer items-center justify-center border-0 bg-transparent p-0"
                        style={{ left: `${u.x}%`, top: `${u.y}%` }}
                      >
                        <span
                          className={cn(
                            "rounded-pill box-content size-[16px] border-[3px] border-solid border-white shadow-[0_2px_6px_rgba(25,31,40,0.25)]",
                            u.ok ? "bg-brand" : "bg-placeholder-icon",
                          )}
                        />
                      </button>
                    ))}

                  {selected && (
                    <div
                      className="pointer-events-none absolute flex -translate-x-1/2 -translate-y-full flex-col items-center"
                      style={{ left: `${selected.x}%`, top: `${selected.y}%` }}
                    >
                      <span className="flex flex-col gap-[2px] rounded-sm bg-white px-[12px] py-[8px] whitespace-nowrap shadow-[0_6px_18px_rgba(25,31,40,0.18)]">
                        <span className="text-[14px] font-extrabold">{selected.name}</span>
                        <span className="text-text-sub text-[12px]">
                          보증금 {selected.deposit} · {selected.rent}
                        </span>
                      </span>
                      <MapPin
                        size={40}
                        strokeWidth={1.5}
                        aria-hidden
                        className="fill-brand mt-[2px] text-white drop-shadow-[0_3px_4px_rgba(25,31,40,0.3)]"
                      />
                    </div>
                  )}

                  <div
                    aria-hidden
                    className="absolute top-[14px] right-[14px] flex flex-col overflow-hidden rounded-sm bg-white shadow-[0_2px_8px_rgba(25,31,40,0.12)]"
                  >
                    <span className="text-text-sub border-line-soft flex size-[40px] items-center justify-center border-b border-solid text-[20px]">
                      +
                    </span>
                    <span className="text-text-sub flex size-[40px] items-center justify-center text-[20px]">
                      −
                    </span>
                  </div>
                  <div className="text-text-sub absolute bottom-[14px] left-[14px] flex gap-[10px] rounded-[10px] bg-white px-[10px] py-[7px] text-[12px]">
                    <span className="inline-flex items-center gap-[5px]">
                      <span className="rounded-pill bg-brand size-[10px]" />
                      신청 가능
                    </span>
                    <span className="inline-flex items-center gap-[5px]">
                      <span className="rounded-pill bg-placeholder-icon size-[10px]" />
                      다른 대상
                    </span>
                  </div>
                </div>

                {selected && (
                  <div
                    aria-live="polite"
                    className="border-line flex flex-wrap items-center justify-between gap-[16px] rounded-[22px] border border-solid px-[22px] py-[20px]"
                  >
                    <div className="flex min-w-0 flex-col gap-[6px]">
                      <span className="flex items-center gap-[8px]">
                        <span className="tracking-title text-[19px] font-extrabold">
                          {selected.name}
                        </span>
                        <span
                          className={cn(
                            "rounded-badge px-[9px] py-[4px] text-[12px] font-bold",
                            selected.ok ? "bg-ok-bg text-ok-text" : "bg-fill text-text-sub",
                          )}
                        >
                          {unitStatus(selected)}
                        </span>
                      </span>
                      <span className="text-text-sub text-[14px]">
                        {selected.addr} · {selected.type} {selected.area} · {selected.floor} ·{" "}
                        {selected.elevator} · {selected.station}
                      </span>
                      <span className="text-[15px]">
                        보증금 <strong>{selected.deposit}</strong> ·{" "}
                        <strong>{selected.rent}</strong> · 준비할 돈{" "}
                        <strong className="text-brand-strong">{selected.prep}</strong>
                      </span>
                    </div>
                    <div className="flex gap-[8px]">
                      <button
                        type="button"
                        className="bg-brand inline-flex min-h-[48px] cursor-pointer items-center gap-[6px] rounded-sm border-0 px-[16px] text-[15px] font-bold text-white"
                      >
                        <ArrowRight size={18} strokeWidth={2.2} aria-hidden />
                        길찾기
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </section>

          <div className="flex flex-wrap items-start gap-[16px]">
            <div
              className="flex min-w-0 flex-col gap-[16px]"
              style={{ flex: `999 1 ${chatOpen ? DETAIL_MAIN_BASIS_WITH_CHAT : 560}px` }}
            >
              <NoticeToc doc={doc} variant="web" />
              <NoticeSections
                doc={doc}
                variant="web"
                onOpenPage={pdfUrl ? openOriginal : undefined}
              />
              <NoticeChat noticeId={n.id} variant="web" />
            </div>

            <aside className="flex min-w-0 flex-col gap-[12px]" style={{ flex: "1 1 360px" }}>
              <section
                aria-label="내 자격"
                className="rounded-card-lg bg-surface flex flex-col px-[26px] pt-[22px] pb-[14px]"
              >
                <div className="flex items-center justify-between">
                  <h2 className="tracking-title m-0 text-[20px] font-extrabold">내 자격</h2>
                  <button
                    type="button"
                    onClick={() => openOriginal(doc.pages.eligibility ?? 1, "신청 자격")}
                    className="text-brand-strong inline-flex min-h-[44px] cursor-pointer items-center border-0 bg-transparent p-0 text-[14px] font-bold"
                  >
                    근거 원문
                  </button>
                </div>
                {n.eligibility.map((e, i) => (
                  <div
                    key={e.label}
                    className={cn(
                      "flex justify-between py-[11px] text-[15px]",
                      i < n.eligibility.length - 1 && "border-line-soft border-b border-solid",
                    )}
                  >
                    <span>{e.label}</span>
                    {e.status === "met" ? (
                      <span className="text-brand-strong font-bold">충족</span>
                    ) : (
                      <Link
                        href={routes.profile}
                        className="text-check-text hover:text-check-text font-bold no-underline"
                      >
                        입력하고 확인
                      </Link>
                    )}
                  </div>
                ))}
              </section>
              {n.ranking && <WebRankCard ranking={n.ranking} className="py-[22px]" />}
              <WebFavoriteButton
                type="NOTICE"
                id={n.id}
                onAdd={() => track("notice_bookmark", noticeParams(n))}
                className="min-h-[58px] text-[17px]"
              />
              <button
                type="button"
                onClick={() => (pdf.open ? pdf.close() : openOriginal())}
                className="rounded-tile bg-surface text-text flex min-h-[54px] cursor-pointer items-center justify-center border-0 text-[16px] font-bold"
              >
                {pdf.open ? "원문 닫기" : `${n.agency} 공고 원문 보기`}
              </button>
              <WebNoticeChatButton
                noticeId={n.id}
                className="rounded-tile bg-surface text-text min-h-[54px]"
              />
            </aside>
          </div>
        </WebMain>
      </div>
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
          variant="web"
        />
      )}
    </WebPage>
  );
}
