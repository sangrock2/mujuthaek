"use client";
import { PreparationButton } from "@/features/preparations/PreparationButton";

import { useDetailTitle } from "@/shared/lib/useDetailTitle";

import {
  NoticeChat,
  WebNoticeChatButton,
  useNoticeChatOpen,
} from "@/features/chat/components/NoticeChat";
import { QueryFeedback } from "@/shared/states/QueryFeedback";
import { ReportButton } from "@/features/report/components/ReportButton";
import { WebFavoriteButton } from "@/features/favorites/components/FavoriteButtons";
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, ChevronRight, FileText, MapPin } from "lucide-react";
import { WebHeader } from "@/shared/layout/WebHeader";
import { WebMain, WebPage } from "@/shared/layout/Responsive";
import { InfiniteScroll, type InfiniteScrollState } from "@/shared/ui/InfiniteScroll";
import { EligibilityCard } from "@/features/notice/components/EligibilityCard";
import { LifeCard } from "@/features/notice/components/LifeCard";
import { NoticeBenefitRow } from "@/features/notice/components/NoticeBenefitRow";
import { NoticeOverview } from "@/features/notice/components/NoticeOverview";
import { WebUnitFilter } from "@/features/notice/components/UnitFilter";
import {
  NoticeHeldBanner,
  NoticeSections,
  NoticeToc,
} from "@/features/notice/components/NoticeSections";
import { NoticeVersions } from "@/features/notice/components/NoticeVersions";
import { PdfViewer } from "@/features/notice/components/PdfViewer";
import { WebRankCard } from "@/features/notice/components/RankCard";
import { noticeOriginal } from "@/features/notice/original";
import { useNoticeJudgment, withMine, type NoticeJudgment } from "@/features/notice/judgment";
import { bySite, directionsUrl, toUnit, useNoticeUnits } from "@/features/notice/units";
import { UnitPrices } from "@/features/notice/components/UnitPrices";
import { UnitPrepValue } from "@/features/notice/components/UnitPrep";
import { SitesMap } from "@/features/notice/components/SitesMap";
import { NoticeLocationSection } from "@/features/notice/components/NoticeLocationSection";
import { noticeParams, useJudgmentViewed } from "@/features/notice/analytics";
import { useNotice, useNoticeBenefits } from "@/features/notice/queries";
import { track } from "@/shared/lib/analytics";
import { usePdfViewer } from "@/features/notice/usePdfViewer";
import { unitStatus, useUnitPicker } from "@/features/notice/useUnitPicker";
import { cn } from "@/shared/lib/cn";
import { routes } from "@/shared/lib/routes";
import type { NoticeSite, NoticeUnit, StandardNotice } from "@/features/notice/mocks/notice";

const sectionTitle = "tracking-title m-0 text-[21px] font-extrabold";

/** 지도 그림 위 블록 이름 */
const mapBlocks = [
  { label: "A-1블록", box: "left-[8%] top-[12%] w-[36%] h-[34%]", text: "left-[10%] top-[14%]" },
  { label: "A-2블록", box: "left-[54%] top-[16%] w-[34%] h-[30%]", text: "left-[56%] top-[18%]" },
  { label: "B-1블록", box: "left-[24%] top-[58%] w-[40%] h-[30%]", text: "left-[26%] top-[60%]" },
];

type BlockUnitsProps = {
  units: NoticeUnit[];
  /** 실제 API: 그림 지도 대신 넣을 지도 (고른 집 · 고르기) */
  map?: (selected: NoticeUnit | null, select: (id: string) => void) => React.ReactNode;
  /** 백엔드에 더 있으면 */
  more?: InfiniteScrollState;
  /** 원본 엑셀 버튼 (목업만) */
  excel?: boolean;
  /** 고른 집 단지의 생활권 카드로 (실제 API) */
  onShowLife?: (siteId: string) => void;
  /** 단지 좌표 (길찾기). 없으면 길찾기를 숨겨요 */
  sites?: NoticeSite[];
};

function BlockUnits({ units, map, more, excel = true, onShowLife, sites }: BlockUnitsProps) {
  const { onlyOk, setOnlyOk, shown, selected, select, countAll, countOk } = useUnitPicker(units);
  const directions = directionsUrl(sites?.find((s) => s.id === selected?.siteId));
  const list = useRef<HTMLDivElement>(null);
  const preview = useRef<HTMLElement>(null);
  const selectedId = selected?.id;
  useEffect(() => {
    preview.current?.scrollTo(0, 0);
  }, [selectedId]);

  return (
    <section
      aria-label="공급 주택 목록"
      className="rounded-card-lg bg-surface flex flex-col gap-[16px] px-[30px] pt-[26px] pb-[30px]"
    >
      <div className="flex flex-wrap items-center justify-between gap-[12px]">
        <div className="flex flex-col gap-[4px]">
          <h2 className={sectionTitle}>
            공급 주택 목록 <span className="text-brand">{countAll}곳</span>
          </h2>
          <span className="text-text-sub text-[14px]">
            {map
              ? "집을 고르면 지도에서 단지 위치를 보여드려요"
              : "집을 고르면 지도에서 위치를 보여드려요"}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-[6px]">
          <WebUnitFilter
            onlyOk={onlyOk}
            setOnlyOk={setOnlyOk}
            countAll={countAll}
            countOk={countOk}
          />
          {excel && (
            <button
              type="button"
              className="text-text-sub inline-flex min-h-[44px] cursor-pointer items-center gap-[4px] border-0 bg-transparent px-[6px] text-[14px] font-bold"
            >
              <FileText size={16} aria-hidden />
              원본 엑셀
            </button>
          )}
        </div>
      </div>

      <div className="grid h-[400px] grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-[14px]">
        <div
          ref={list}
          role="region"
          aria-label="주택 목록"
          tabIndex={0}
          className="min-h-0 min-w-0 overflow-y-auto overscroll-contain p-0.5 pr-2"
        >
          <div className="flex flex-col gap-[8px]">
            {bySite(shown).map((g) => (
              <div key={g.key} role="group" aria-label={g.name} className="flex flex-col gap-[8px]">
                {g.name && (
                  <h3 className="text-text-sub bg-surface sticky top-0 z-[1] m-0 py-[4px] text-[14px] font-extrabold">
                    {g.name} <span className="text-brand">{g.count}호</span>
                    {g.lifeScore !== undefined && (
                      <span className="text-text-tertiary font-bold">
                        {" "}
                        · 생활권 {g.lifeScore}점
                      </span>
                    )}
                  </h3>
                )}
                {g.units.map((u) => {
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
                      <span className="flex w-full items-center justify-between gap-[8px]">
                        <span className="text-[15px] font-bold">
                          {g.name ? (u.label ?? u.name) : u.name}
                        </span>
                        <span
                          className={cn(
                            "rounded-badge flex-none px-[8px] py-[3px] text-[12px] font-bold",
                            u.ok ? "bg-ok-bg text-ok-text" : "bg-fill text-text-sub",
                          )}
                        >
                          {unitStatus(u)}
                        </span>
                      </span>
                      <span className="text-text-sub text-[13px]">
                        {u.type} · {u.area} · {u.floor}
                      </span>
                      <UnitPrices unit={u} />
                    </button>
                  );
                })}
              </div>
            ))}
            {more && <InfiniteScroll data={more} label="주택" scrollRoot={list} />}
          </div>
        </div>

        <section
          ref={preview}
          aria-label="선택한 주택 상세"
          tabIndex={0}
          className="min-h-0 min-w-0 overflow-y-auto overscroll-contain pr-2"
        >
          <div className="flex min-w-0 flex-col gap-[12px]">
            {map ? (
              <div className="flex min-w-0">{map(selected, select)}</div>
            ) : (
              <div
                aria-label="주택 위치 지도"
                role="group"
                className="bg-map-road relative h-[230px] min-w-0 overflow-hidden rounded-[20px]"
              >
                {mapBlocks.map((b) => (
                  <span
                    key={b.label}
                    aria-hidden
                    className={cn("bg-map-road-2 absolute rounded-[18px]", b.box)}
                  />
                ))}
                <span
                  aria-hidden
                  className="bg-map-park absolute top-[56%] left-[70%] h-[26%] w-[22%] rounded-[45%_55%_50%_50%]"
                />
                <span aria-hidden className="absolute top-1/2 right-0 left-0 h-[10px] bg-white" />
                <span aria-hidden className="absolute top-0 bottom-0 left-[49%] w-[9px] bg-white" />
                {mapBlocks.map((b) => (
                  <span
                    key={b.label}
                    aria-hidden
                    className={cn("text-text-tertiary absolute text-[12px] font-bold", b.text)}
                  >
                    {b.label}
                  </span>
                ))}
                <span
                  aria-hidden
                  className="text-brand-strong absolute top-[66%] left-[73%] text-[12px]"
                >
                  근린공원
                </span>
                <span
                  aria-hidden
                  className="rounded-tag text-text-sub absolute top-[52%] left-[51%] bg-white px-[6px] py-[2px] text-[12px] font-bold"
                >
                  ○○역
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
                    <span className="flex flex-col gap-[2px] rounded-sm bg-white px-[11px] py-[7px] whitespace-nowrap shadow-[0_6px_18px_rgba(25,31,40,0.18)]">
                      <span className="text-[13px] font-extrabold">{selected.name}</span>
                      <span className="text-text-sub text-[12px]">
                        {selected.deposit} · {selected.rent}
                      </span>
                    </span>
                    <MapPin
                      size={36}
                      strokeWidth={1.5}
                      aria-hidden
                      className="fill-brand mt-[2px] text-white drop-shadow-[0_3px_4px_rgba(25,31,40,0.3)]"
                    />
                  </div>
                )}

                <div className="text-text-sub absolute bottom-[12px] left-[12px] flex gap-[10px] rounded-[10px] bg-white px-[10px] py-[6px] text-[12px]">
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
            )}
            {selected && (
              <div
                aria-live="polite"
                className="bg-bg flex flex-wrap items-center justify-between gap-[14px] rounded-[20px] px-[20px] py-[18px]"
              >
                <div className="flex min-w-0 flex-col gap-[5px]">
                  <span className="flex flex-wrap items-center gap-[8px]">
                    <span className="tracking-title text-[18px] font-extrabold">
                      {selected.name}
                    </span>
                    <span
                      className={cn(
                        "rounded-badge px-[8px] py-[3px] text-[12px] font-bold",
                        selected.ok ? "bg-ok-bg text-ok-text" : "bg-surface text-text-sub",
                      )}
                    >
                      {unitStatus(selected)}
                    </span>
                  </span>
                  <span className="text-text-sub text-[14px]">
                    {[`${selected.type} ${selected.area}`, selected.floor, selected.station]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                  {selected.prices ? (
                    <>
                      {selected.prices.map((p) => (
                        <span key={p.target} className="text-[15px]">
                          <span className="text-text-sub mr-[6px] text-[14px]">{p.target}</span>
                          보증금 <strong>{p.deposit}</strong> · <strong>{p.rent}</strong>
                        </span>
                      ))}
                      <span className="text-[15px]">
                        준비할 돈 <UnitPrepValue unit={selected} />
                      </span>
                    </>
                  ) : (
                    <span className="text-[15px]">
                      보증금 <strong>{selected.deposit}</strong> · <strong>{selected.rent}</strong>{" "}
                      · 준비할 돈 <UnitPrepValue unit={selected} />
                    </span>
                  )}
                </div>
                <div className="flex gap-[8px]">
                  {onShowLife && selected.siteId && selected.lifeScore !== undefined && (
                    <button
                      type="button"
                      onClick={() => onShowLife(selected.siteId!)}
                      className="text-text inline-flex min-h-[46px] cursor-pointer items-center gap-[6px] rounded-sm border-0 bg-white px-[14px] text-[14px] font-bold"
                    >
                      <MapPin size={17} aria-hidden />이 집 생활권 {selected.lifeScore}점
                    </button>
                  )}
                  {directions && (
                    <a
                      href={directions}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="bg-brand inline-flex min-h-[46px] items-center gap-[6px] rounded-sm px-[14px] text-[14px] font-bold text-white no-underline hover:text-white"
                    >
                      <ArrowRight size={17} strokeWidth={2.2} aria-hidden />
                      길찾기
                    </a>
                  )}
                </div>
              </div>
            )}
          </div>
        </section>
      </div>
    </section>
  );
}

/** 실제 API 주택목록: 호별 목록 + 단지 위치 지도 */
function ApiBlockUnits({
  notice,
  judgment,
  onShowLife,
}: {
  notice: StandardNotice;
  judgment: NoticeJudgment | null;
  onShowLife: (siteId: string) => void;
}) {
  const q = useNoticeUnits(notice.id, true);
  const sites = useMemo(() => notice.sites ?? [], [notice.sites]);
  const units = useMemo(
    () => (q.data?.pages ?? []).flatMap((p) => p.items.map((u) => toUnit(u, sites, judgment))),
    [q.data, sites, judgment],
  );
  if (q.isPending || units.length === 0) return <NoticeLocationSection sites={sites} />;
  return (
    <BlockUnits
      units={units}
      excel={false}
      onShowLife={onShowLife}
      sites={sites}
      more={q.pagination}
      map={(selected, select) => (
        <SitesMap
          sites={sites}
          selectedSiteId={selected?.siteId}
          onSelectSite={(siteId) => {
            const first = units.find((u) => u.siteId === siteId);
            if (first) select(first.id);
          }}
          className="h-[230px] w-full"
        />
      )}
    />
  );
}

export function WebDetail({ id }: { id: string }) {
  const { data, loading, error } = useNotice(id);
  const n = data?.kind === "standard" ? data : undefined;
  const relatedBenefits = useNoticeBenefits(id, Boolean(n));
  useDetailTitle(n?.title);
  const j = useNoticeJudgment(n);
  const pdf = usePdfViewer();
  // 채팅 패널이 열린 동안은 본문 기본 폭을 줄여서 오른쪽 칸(내 자격 · 이야기 닫기)이 본문 아래로 내려가지 않게 해요
  const chatOpen = useNoticeChatOpen(n?.id ?? id);
  useJudgmentViewed(id, n);
  const [lifeSite, setLifeSite] = useState<string>();
  if (!n) {
    return (
      <WebPage>
        <WebHeader mode="home" current={routes.homes} />
        <WebMain className="pt-[24px] pb-[80px]">
          {(loading || error) && (
            <QueryFeedback error={error} label="공고" queryKey={["notice", "detail", id]} />
          )}
        </WebMain>
      </WebPage>
    );
  }
  const doc = withMine(n.doc, j.judgment?.mineTypes ?? []);
  const money = j.judgment?.money;
  const benefits = relatedBenefits.data ?? n.benefits ?? [];
  /** 원문 PDF가 있으면 근거의 PDF·쪽·문장을 옆에 열고, 없으면 기관 사이트로 */
  const original = noticeOriginal(
    doc,
    pdf,
    (via) => track("notice_source_open", { ...noticeParams(n), via }),
    j.judgment,
  );
  const openOriginal = original.openOriginal;
  const pdfUrl = original.viewer?.src;
  /** 주택목록에서 고른 집 단지의 생활권으로 */
  const showLife = (siteId: string) => {
    setLifeSite(siteId);
    document.getElementById("life")?.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
    });
  };

  return (
    <WebPage>
      <div className="flex flex-1 flex-col">
        <WebHeader mode="home" current={routes.homes} />
        <WebMain className="gap-[16px] pt-[22px] pb-[64px]">
          <nav
            aria-label="위치"
            className="text-text-tertiary flex min-w-0 items-center gap-[6px] text-[14px]"
          >
            <Link
              href={routes.homes}
              className="text-text-sub hover:text-text-sub inline-flex min-h-[36px] shrink-0 items-center font-semibold no-underline"
            >
              주거 공고
            </Link>
            <ChevronRight size={16} className="shrink-0" aria-hidden />
            <span aria-current="page" className="truncate">
              {n.title}
            </span>
          </nav>

          <NoticeOverview
            notice={n}
            verdict={j.judgment?.verdict}
            variant="web"
            onOpenPdf={original.hasPdf ? () => openOriginal() : undefined}
          />

          <div
            className={cn(
              "grid items-start gap-[24px]",
              chatOpen ? "grid-cols-1" : "grid-cols-[minmax(0,1fr)_320px]",
            )}
          >
            <div className="flex min-w-0 flex-col gap-[16px]">
              {/* 이 공고 이야기 창 (여는 곳은 오른쪽 「이야기」 단추) */}
              <NoticeChat noticeId={n.id} variant="web" />

              <NoticeHeldBanner doc={doc} variant="web" onOpenReview={original.openReview} />
              <NoticeVersions noticeId={n.id} variant="web" />
              <NoticeToc doc={doc} variant="web" />
              <NoticeSections
                doc={doc}
                variant="web"
                onOpenPage={original.hasPdf ? openOriginal : undefined}
                onOpenReview={original.openReview}
                reviewIds={new Set(original.reviewItems.map((item) => item.id))}
              />

              {n.units && n.units.length > 0 && <BlockUnits units={n.units} />}
              {n.hasUnits ? (
                <ApiBlockUnits notice={n} judgment={j.judgment} onShowLife={showLife} />
              ) : (
                <NoticeLocationSection sites={n.sites ?? []} />
              )}

              {n.life && (
                <LifeCard
                  life={n.life}
                  variant="web"
                  siteId={lifeSite}
                  onSiteChange={setLifeSite}
                />
              )}

              {benefits.length > 0 && (
                <section
                  aria-label="이 공고와 함께 확인할 혜택"
                  className="rounded-card-lg bg-surface flex flex-col px-[30px] pt-[24px] pb-[14px]"
                >
                  <div className="mb-[8px]">
                    <h2 className={sectionTitle}>이 공고와 함께 확인할 혜택</h2>
                    <p className="text-text-sub mt-1 text-[13px]">
                      {n.benefitArea ? `${n.benefitArea} 입주` : "입주"}에 관련된 주거비·이사비
                      지원을 모았어요.
                    </p>
                  </div>
                  {benefits.map((b, i) => (
                    <NoticeBenefitRow key={b.id} benefit={b} divided={i < benefits.length - 1} />
                  ))}
                </section>
              )}
            </div>

            {/* 내 자격·관심 등록·원문 보기는 처음 자리에 붙어 있어서 본문을 내려도 움직이지 않아요(두 칸이 나란할 때만).
                화면보다 길면 보이는 스크롤바로 이 칸 전체를 내려볼 수 있어요 */}
            <aside className="sticky top-[93px] flex max-h-[calc(100dvh-117px)] min-w-0 flex-col gap-[16px] overflow-y-auto overscroll-contain pb-[8px]">
              <EligibilityCard
                judgment={j.judgment}
                loading={j.loading}
                error={j.error}
                variant="web"
                onOpenOriginal={original.openEligibility}
                onOpenReview={original.openReview}
              />

              {n.ranking && <WebRankCard ranking={n.ranking} />}

              {money && (
                <section
                  aria-label="내가 준비할 돈"
                  className="rounded-card-lg bg-surface flex flex-col gap-[10px] p-[26px]"
                >
                  <h2 className="tracking-title mx-0 mt-0 mb-[4px] text-[20px] font-extrabold">
                    예상 준비할 돈 · {money.type}
                  </h2>
                  <div className="text-text-sub flex justify-between text-[15px]">
                    <span>임대보증금</span>
                    <span>{money.deposit}</span>
                  </div>
                  {money.loan && (
                    <div className="text-text-sub flex justify-between text-[15px]">
                      <span>{money.loanName}</span>
                      <span>− {money.loan}</span>
                    </div>
                  )}
                  <div className="border-line mt-[4px] flex items-baseline justify-between border-t border-solid pt-[14px]">
                    <span className="text-[16px] font-bold">예상 준비할 돈</span>
                    <span className="tracking-h1 text-[30px] font-extrabold">{money.prep}</span>
                  </div>
                  <span className="text-[13px] leading-[1.5]">
                    대출 예상액을 뺀 참고 금액이에요. 실제 승인액·금리·부대비용에 따라 달라져요.
                  </span>
                  {money.note && <span className="text-text-sub text-[14px]">{money.note}</span>}
                  {/* 대출 예상은 구간 값으로 본 것이라, 정확한 소득·순자산으로 다시 보는 화면으로 */}
                  {money.loan && (
                    <Link
                      href={routes.loans}
                      className="text-brand-strong inline-flex min-h-[44px] items-center self-start text-[14px] font-bold no-underline"
                    >
                      대출 자격 정확히 확인하기 →
                    </Link>
                  )}
                </section>
              )}

              {/* 행동과 안내도 같은 스크롤 흐름에 두어 준비할 돈을 가리지 않아요. */}
              <div className="rounded-card-lg border-line-soft bg-surface flex flex-col gap-2.5 border p-4">
                <PreparationButton noticeId={n.id} />
                <WebFavoriteButton
                  type="NOTICE"
                  id={n.id}
                  onAdd={() => track("notice_bookmark", noticeParams(n))}
                />
                <button
                  type="button"
                  aria-pressed={pdfUrl ? pdf.open : undefined}
                  onClick={() => (pdf.open ? pdf.close() : openOriginal())}
                  className="rounded-control bg-fill text-text flex min-h-[48px] cursor-pointer items-center justify-center gap-[6px] border-0 text-[16px] font-bold"
                >
                  <FileText size={18} aria-hidden />
                  {pdf.open ? "원문 닫기" : `${n.agency} 공고 원문 보기`}
                </button>
                <WebNoticeChatButton
                  noticeId={n.id}
                  className="rounded-control bg-fill text-text min-h-[48px]"
                />
                <div className="flex flex-col items-center gap-[2px] pt-[4px]">
                  <span className="text-text-sub text-[13px]">
                    판정은 참고용이에요. 신청 전에 원문을 확인해 주세요
                  </span>
                  <ReportButton
                    target={{ kind: "notice", id: n.id }}
                    screen="공고 상세"
                    className="self-stretch"
                    buttonClassName="text-[13px]"
                  />
                </div>
              </div>
            </aside>
          </div>
        </WebMain>
      </div>
      {original.viewer && (
        <PdfViewer
          {...original.viewer}
          notice={{ title: n.title, summary: doc.summary }}
          variant="web"
        />
      )}
    </WebPage>
  );
}
