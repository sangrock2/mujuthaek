"use client";
import { PreparationButton } from "@/features/preparations/PreparationButton";

import { useDetailTitle } from "@/shared/lib/useDetailTitle";

import {
  DETAIL_MAIN_BASIS_WITH_CHAT,
  NoticeChat,
  WebNoticeChatButton,
  useNoticeChatOpen,
} from "@/features/chat/components/NoticeChat";
import { QueryFeedback } from "@/shared/states/QueryFeedback";
import { ReportButton } from "@/features/report/components/ReportButton";
import { WebFavoriteButton } from "@/features/favorites/components/FavoriteButtons";
import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, ChevronRight, FileText, MapPin } from "lucide-react";
import { WebHeader } from "@/shared/layout/WebHeader";
import { WebMain, WebPage } from "@/shared/layout/Responsive";
import { EligibilityCard } from "@/features/notice/components/EligibilityCard";
import { LifeCard } from "@/features/notice/components/LifeCard";
import { NoticeTags } from "@/features/notice/components/NoticeTags";
import { WebUnitFilter } from "@/features/notice/components/UnitFilter";
import {
  NoticeHeldBanner,
  NoticeSections,
  NoticeToc,
} from "@/features/notice/components/NoticeSections";
import { NoticeVersions } from "@/features/notice/components/NoticeVersions";
import { PdfViewer } from "@/features/notice/components/PdfViewer";
import { RegulationNotice } from "@/features/notice/components/RegulationNotice";
import { WebRankCard } from "@/features/notice/components/RankCard";
import { VerdictBadge } from "@/shared/ui/Badge";
import { dueText, formatPeriod, statusLabel } from "@/features/notice/format";
import { noticeOriginal } from "@/features/notice/original";
import { useNoticeJudgment, withMine, type NoticeJudgment } from "@/features/notice/judgment";
import { bySite, directionsUrl, toUnit, useNoticeUnits } from "@/features/notice/units";
import { UnitPrices } from "@/features/notice/components/UnitPrices";
import { UnitPrepValue } from "@/features/notice/components/UnitPrep";
import { SitesMap } from "@/features/notice/components/SitesMap";
import { noticeParams, useJudgmentViewed } from "@/features/notice/analytics";
import { useNotice } from "@/features/notice/queries";
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
  more?: { onClick: () => void; loading: boolean };
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

      <div className="flex flex-wrap items-stretch gap-[14px]">
        <div
          role="group"
          aria-label="주택 목록"
          className="box-content flex max-h-[400px] min-w-0 flex-col gap-[8px] overflow-y-auto pr-[2px]"
          style={{ flex: "1 1 270px" }}
        >
          {bySite(shown).map((g) => (
            <div key={g.key} role="group" aria-label={g.name} className="flex flex-col gap-[8px]">
              {g.name && (
                <h3 className="text-text-sub bg-surface sticky top-0 z-[1] m-0 py-[4px] text-[14px] font-extrabold">
                  {g.name} <span className="text-brand">{g.count}호</span>
                  {g.lifeScore !== undefined && (
                    <span className="text-text-tertiary font-bold"> · 생활권 {g.lifeScore}점</span>
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
          {more && (
            <button
              type="button"
              onClick={more.onClick}
              disabled={more.loading}
              className="bg-fill text-text min-h-[44px] flex-none cursor-pointer rounded-sm border-0 text-[14px] font-bold disabled:opacity-60"
            >
              {more.loading ? "불러오는 중" : "더 보기"}
            </button>
          )}
        </div>

        {map ? (
          <div className="flex min-w-0" style={{ flex: "999 1 360px" }}>
            {map(selected, select)}
          </div>
        ) : (
          <div
            aria-label="주택 위치 지도"
            role="group"
            className="bg-map-road relative h-[400px] min-w-0 overflow-hidden rounded-[20px]"
            style={{ flex: "999 1 360px" }}
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
      </div>

      {selected && (
        <div
          aria-live="polite"
          className="bg-bg flex flex-wrap items-center justify-between gap-[14px] rounded-[20px] px-[20px] py-[18px]"
        >
          <div className="flex min-w-0 flex-col gap-[5px]">
            <span className="flex flex-wrap items-center gap-[8px]">
              <span className="tracking-title text-[18px] font-extrabold">{selected.name}</span>
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
                보증금 <strong>{selected.deposit}</strong> · <strong>{selected.rent}</strong> ·
                준비할 돈 <UnitPrepValue unit={selected} />
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
                rel="noreferrer"
                className="bg-brand inline-flex min-h-[46px] items-center gap-[6px] rounded-sm px-[14px] text-[14px] font-bold text-white no-underline hover:text-white"
              >
                <ArrowRight size={17} strokeWidth={2.2} aria-hidden />
                길찾기
              </a>
            )}
          </div>
        </div>
      )}
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
  if (q.isPending || units.length === 0) return null;
  return (
    <BlockUnits
      units={units}
      excel={false}
      onShowLife={onShowLife}
      sites={sites}
      more={
        q.hasNextPage
          ? { onClick: () => void q.fetchNextPage(), loading: q.isFetchingNextPage }
          : undefined
      }
      map={(selected, select) => (
        <SitesMap
          sites={sites}
          selectedSiteId={selected?.siteId}
          onSelectSite={(siteId) => {
            const first = units.find((u) => u.siteId === siteId);
            if (first) select(first.id);
          }}
          className="h-[400px] w-full"
        />
      )}
    />
  );
}

export function WebDetail({ id }: { id: string }) {
  const { data, loading, error } = useNotice(id);
  const n = data?.kind === "standard" ? data : undefined;
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
  const benefits = n.benefits ?? [];
  /** 원문 PDF가 있으면 근거의 PDF·쪽·문장을 옆에 열고, 없으면 기관 사이트로 */
  const original = noticeOriginal(doc, pdf, (via) =>
    track("notice_source_open", { ...noticeParams(n), via }),
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
      <div
        className={cn(
          "flex flex-1 flex-col [overflow-anchor:none]",
          pdf.open && pdfUrl && "pl-[min(46vw,680px)]",
        )}
      >
        {/* 상단 바는 화면마다 위에 붙어 있어요(높이 69px: 오른쪽 칸이 그 아래에 붙어요) */}
        <WebHeader mode="home" current={routes.homes} />
        <WebMain className="gap-[20px] pt-[24px] pb-[80px]">
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

          <div
            className={cn(
              "grid items-start gap-[24px]",
              pdf.open || chatOpen ? "grid-cols-1" : "grid-cols-[minmax(0,1fr)_320px]",
            )}
          >
            <div
              className="flex min-w-0 flex-col gap-[16px]"
              style={{ flex: `999 1 ${chatOpen ? DETAIL_MAIN_BASIS_WITH_CHAT : 600}px` }}
            >
              <section
                aria-label="공고 요약"
                className="rounded-card-lg bg-surface overflow-hidden"
              >
                <div className="flex flex-col gap-[20px] px-[30px] pt-[28px] pb-[30px]">
                  <div className="flex flex-col gap-[10px]">
                    <NoticeTags
                      verdict={j.judgment?.verdict ?? "check"}
                      rank={n.ranking?.myRank}
                      due={dueText(n)}
                      tags={n.tags}
                      size="lg"
                    />
                    <h1 className="tracking-h1 m-0 text-[34px] font-extrabold">{n.title}</h1>
                    <span className="text-text-sub text-[16px]">{n.meta}</span>
                    {doc.summary && <p className="m-0 text-[16px] leading-[1.6]">{doc.summary}</p>}
                  </div>
                  <dl
                    className="m-0 grid gap-[10px]"
                    style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}
                  >
                    {n.facts.map((f) => (
                      <div key={f.label} className="bg-bg rounded-tile px-[18px] py-[16px]">
                        <dt className="text-text-sub text-[13px]">{f.label}</dt>
                        <dd className="mx-0 mt-[4px] mb-0 text-[17px] font-bold">{f.value}</dd>
                      </div>
                    ))}
                  </dl>
                  {doc.applyPeriod && (
                    <div className="border-line-soft flex flex-wrap items-baseline gap-x-[14px] gap-y-[4px] border-t border-solid pt-[18px]">
                      <span className="text-text-sub text-[14px]">신청 기간</span>
                      <span className="text-[18px] font-extrabold">
                        {formatPeriod(doc.applyPeriod.start, doc.applyPeriod.end)}
                      </span>
                      <span className="text-brand-strong text-[14px] font-bold">
                        {statusLabel[doc.status]}
                      </span>
                      {doc.applyPeriod.note && (
                        <span className="text-text-sub text-[14px]">{doc.applyPeriod.note}</span>
                      )}
                    </div>
                  )}
                  <RegulationNotice noticeId={n.id} variant="web" />
                </div>
              </section>

              {/* 이 공고 이야기 창 (여는 곳은 오른쪽 「이야기」 단추) */}
              <NoticeChat noticeId={n.id} variant="web" />

              <NoticeHeldBanner doc={doc} variant="web" />
              <NoticeVersions noticeId={n.id} variant="web" />
              <NoticeToc doc={doc} variant="web" />
              <NoticeSections
                doc={doc}
                variant="web"
                onOpenPage={original.hasPdf ? openOriginal : undefined}
              />

              {n.units && n.units.length > 0 && <BlockUnits units={n.units} />}
              {n.hasUnits && (
                <ApiBlockUnits notice={n} judgment={j.judgment} onShowLife={showLife} />
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
                  aria-label="이 지역 정책"
                  className="rounded-card-lg bg-surface flex flex-col px-[30px] pt-[24px] pb-[14px]"
                >
                  <div className="mb-[8px] flex items-baseline justify-between">
                    <h2 className={sectionTitle}>입주하면 받을 수 있는 혜택</h2>
                    <span className="text-text-tertiary text-[13px]">
                      {n.benefitArea} · 내 조건 판정
                    </span>
                  </div>
                  {benefits.map((b, i) => (
                    <Link
                      key={b.id}
                      href={routes.benefit(b.id)}
                      className={cn(
                        "text-text hover:text-text flex items-center gap-[14px] py-[14px] no-underline",
                        i < benefits.length - 1 && "border-line-soft border-b border-solid",
                      )}
                    >
                      <span className="flex flex-1 flex-col gap-[2px]">
                        <span className="text-[16px] font-bold">{b.title}</span>
                        <span className="text-text-sub text-[14px]">{b.desc}</span>
                      </span>
                      <VerdictBadge verdict={b.verdict} />
                      <ChevronRight size={18} className="text-text-tertiary" aria-hidden />
                    </Link>
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
              <div className="bg-bg flex flex-col gap-[16px]">
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
                  className="rounded-tile bg-surface text-text flex min-h-[56px] cursor-pointer items-center justify-center gap-[6px] border-0 text-[16px] font-bold"
                >
                  <FileText size={18} aria-hidden />
                  {pdf.open ? "원문 닫기" : `${n.agency} 공고 원문 보기`}
                </button>
                <WebNoticeChatButton
                  noticeId={n.id}
                  className="rounded-tile bg-surface text-text min-h-[56px]"
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
      {original.viewer && <PdfViewer {...original.viewer} variant="web" />}
    </WebPage>
  );
}
